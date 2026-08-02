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
import json
import os
import random
import threading

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


def run_with_timeout(fn, seconds):
    # Some reference solutions loop forever on inputs the published tests never
    # reach. The thread is a daemon so a hung one dies with the process instead
    # of holding it open.
    result = []
    thread = threading.Thread(target=lambda: result.append(fn()), daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive() or not result:
        return None
    return result[0]


def survivors(reference, candidates):
    # Keeps the inputs the reference actually handles.
    def check():
        kept = []
        for args in candidates:
            try:
                reference(*args)
            except Exception:
                continue
            kept.append(args)
        return kept

    return run_with_timeout(check, 10) or []


def make_tasks(limit=100, hidden=3, oracle=50, seed=0):
    rng = random.Random(seed)
    tasks = []

    if not os.path.exists(DATA):
        raise SystemExit(f"{DATA} is missing. Download it with\n"
                         "  python fetch_mbpp.py")

    with open(DATA, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    for record in records:
        if len(tasks) >= limit:
            break

        parsed = [parse_assert(t) for t in record["test_list"]]
        if any(p is None for p in parsed):
            continue
        names = {p[0] for p in parsed}
        if len(names) != 1:
            continue
        name = names.pop()
        visible = [p[1] for p in parsed]

        try:
            reference = build_reference(record, name)
        except Exception:
            continue

        # The reference has to satisfy the problem's own published tests,
        # otherwise it is not usable as ground truth.
        agrees = run_with_timeout(
            lambda: all(reference(*p[1]) == p[2] for p in parsed), 5)
        if not agrees:
            continue

        wanted = hidden + oracle
        candidates = []
        for _ in range(wanted * 4):
            if len(candidates) >= wanted:
                break
            args = fuzz_args(visible, rng)
            if args is not None and args not in visible:
                candidates.append(args)

        kept = survivors(reference, candidates)
        if len(kept) < hidden + 10:
            continue

        tasks.append({
            "name": f"{name}_{record['task_id']}",
            "reference": reference,
            "visible_tests": visible,
            "hidden_tests": kept[:hidden],
            "oracle_inputs": kept[hidden:] + survivors(reference, edge_args(visible)),
            "description": record["text"],
        })

    return tasks
