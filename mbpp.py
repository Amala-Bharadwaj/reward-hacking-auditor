# Builds auditor tasks out of real MBPP problems.
#
# MBPP gives each problem a reference solution and three published assert
# statements. Those three asserts are the whole test suite and they are also
# shown to the solver, so they are exactly the visible tests the auditor
# attacks. Hidden tests are fuzzed inputs that look like the published ones.
# Oracle inputs are those plus deliberate edge cases.
#
# The reference solutions are executed. MBPP is a well known public dataset but
# this is still running downloaded code, so keep the file you audit under your
# own control.

import ast
import collections
import copy
import json
import multiprocessing
import os
import random

DATA = "data_mbpp.jsonl"


def parse_assert(line):
    # Pulls the function name, the argument tuple and the expected answer out of
    # "assert f(a, b) == c". Returns None for anything that is not that shape.
    node = ast.parse(line.strip()).body[0]
    if not isinstance(node, ast.Assert):
        return None
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.Eq):
        return None
    call = test.left
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    if call.keywords:
        return None
    try:
        args = tuple(ast.literal_eval(a) for a in call.args)
        expected = ast.literal_eval(test.comparators[0])
    except Exception:
        return None
    return call.func.id, args, expected


def build_reference(record, name):
    namespace = {}
    exec(record.get("test_setup_code") or "", namespace)
    exec(record["code"], namespace)
    return namespace[name]


def fuzz(samples, rng):
    # Makes a new value that looks like the values seen at this argument
    # position. Returns None if the type is one we do not generate.
    base = rng.choice(samples)

    if isinstance(base, bool):
        return rng.random() < 0.5

    if isinstance(base, int):
        seen = [s for s in samples if isinstance(s, int) and not isinstance(s, bool)]
        lo, hi = min(seen), max(seen)
        span = max(1, hi - lo)
        low = 0 if lo >= 0 else lo - span
        return rng.randint(max(low, -500), min(hi + span, 500))

    if isinstance(base, float):
        seen = [s for s in samples if isinstance(s, float)]
        return round(rng.uniform(min(seen) - 1, max(seen) + 1), 3)

    if isinstance(base, str):
        seen = [s for s in samples if isinstance(s, str)]
        chars = sorted(set("".join(seen))) or list("abcdefghij")
        length = rng.randint(max(1, min(len(s) for s in seen) - 1),
                             max(len(s) for s in seen) + 2)
        return "".join(rng.choice(chars) for _ in range(length))

    if isinstance(base, (list, tuple)):
        seen = [s for s in samples if isinstance(s, (list, tuple))]
        elements = [e for s in seen for e in s]
        if not elements:
            return type(base)()
        length = rng.randint(1, max(1, max(len(s) for s in seen) + 1))
        out = []
        for _ in range(length):
            value = fuzz(elements, rng)
            if value is None:
                return None
            out.append(value)
        return type(base)(out)

    return None


def fuzz_args(arg_tuples, rng):
    out = []
    for samples in zip(*arg_tuples):
        value = fuzz(list(samples), rng)
        if value is None:
            return None
        out.append(value)
    return tuple(out)


def edge_args(arg_tuples):
    # One edge value swapped into one position at a time. These go into the
    # oracle only, never into the hidden tests, so the strong verifier gets no
    # unfair credit for them.
    out = []
    base = arg_tuples[0]
    for i, value in enumerate(base):
        edges = []
        if isinstance(value, str):
            edges = ["", value[:1]]
        elif isinstance(value, (list, tuple)):
            edges = [type(value)(), type(value)(list(value)[:1])]
        elif isinstance(value, bool):
            edges = [True, False]
        elif isinstance(value, int):
            edges = [0, 1, -1]
        elif isinstance(value, float):
            edges = [0.0, -1.0]
        for edge in edges:
            args = list(base)
            args[i] = edge
            out.append(tuple(args))
    return out


def keep_handled(reference, candidates):
    kept = []
    for args in candidates:
        try:
            reference(*copy.deepcopy(args))
        except Exception:
            continue
        kept.append(args)
    return kept


def vet(job):
    # Runs in the worker process. Checks the reference against its own published
    # tests, then reports which generated inputs it handles.
    setup, code, name, checks, candidates, edges = job
    try:
        namespace = {}
        exec(setup, namespace)
        exec(code, namespace)
        reference = namespace[name]
    except Exception:
        return "reference will not import", [], []

    try:
        if not all(reference(*copy.deepcopy(args)) == expected
                   for args, expected in checks):
            return "reference fails its own tests", [], []
    except Exception:
        return "reference fails its own tests", [], []

    return "ok", keep_handled(reference, candidates), keep_handled(reference, edges)


class Vetter:
    # Some reference solutions loop forever on inputs their published tests never
    # reach. They run in a worker process so a hung one can be killed. A thread
    # cannot be killed, and on a full dataset run the stuck threads pile up and
    # starve the real work.

    def __init__(self, seconds=15):
        self.seconds = seconds
        self.pool = None

    def run(self, job):
        if self.pool is None:
            self.pool = multiprocessing.Pool(1)
        try:
            return self.pool.apply_async(vet, (job,)).get(self.seconds)
        except multiprocessing.TimeoutError:
            self.pool.terminate()
            self.pool = None
            return None
        except Exception:
            return None

    def close(self):
        if self.pool is not None:
            self.pool.terminate()
            self.pool = None


def make_tasks(limit=None, hidden=3, oracle=50, seed=0):
    # limit=None audits every problem in the file. skipped records why each
    # dropped problem dropped, so the coverage of the final number is checkable.
    rng = random.Random(seed)
    tasks = []
    skipped = collections.Counter()
    vetter = Vetter()

    if not os.path.exists(DATA):
        raise SystemExit(f"{DATA} is missing. Download it with\n"
                         "  python fetch_mbpp.py")

    with open(DATA, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    for record in records:
        if limit is not None and len(tasks) >= limit:
            break

        parsed = [parse_assert(t) for t in record["test_list"]]
        if any(p is None for p in parsed):
            skipped["assert not a plain call"] += 1
            continue
        names = {p[0] for p in parsed}
        if len(names) != 1:
            skipped["tests call different functions"] += 1
            continue
        name = names.pop()
        visible = [p[1] for p in parsed]

        wanted = hidden + oracle
        candidates = []
        for _ in range(wanted * 4):
            if len(candidates) >= wanted:
                break
            args = fuzz_args(visible, rng)
            if args is not None and args not in visible:
                candidates.append(args)

        # The reference has to satisfy the problem's own published tests,
        # otherwise it is not usable as ground truth.
        job = (record.get("test_setup_code") or "", record["code"], name,
               [(p[1], p[2]) for p in parsed], candidates, edge_args(visible))
        result = vetter.run(job)
        if result is None:
            skipped["reference hangs"] += 1
            continue
        status, kept, kept_edges = result
        if status != "ok":
            skipped[status] += 1
            continue
        if len(kept) < hidden + 10:
            skipped["too few fuzzed inputs survive"] += 1
            continue

        try:
            reference = build_reference(record, name)
        except Exception:
            skipped["reference will not import"] += 1
            continue

        tasks.append({
            "benchmark": "mbpp",
            "name": f"{name}_{record['task_id']}",
            "reference": reference,
            # Source is kept so attributes.py can mutate the reference. The
            # callable alone is not enough to compute a mutation score.
            "source": record["code"],
            "func_name": name,
            "visible_tests": visible,
            "hidden_tests": kept[:hidden],
            "oracle_inputs": kept[hidden:] + kept_edges,
            "edge_tests": kept_edges,
            "description": record["text"],
        })

    vetter.close()
    print(f"{len(tasks)} usable tasks out of {len(records)} problems")
    for reason, count in skipped.most_common():
        print(f"  skipped {count:4d}  {reason}")
    return tasks
