# Builds auditor tasks out of HumanEval problems.
#
# HumanEval ships a canonical solution and a check(candidate) function rather
# than a list of asserts. The asserts live inside check, calling either
# `candidate` or the entry point by name, so they are pulled out of the AST
# instead of parsed a line at a time.
#
# Everything downstream is imported from mbpp so the two benchmarks are measured
# by the same code. Only the parsing and the source assembly differ.
#
# Run it with  python humaneval.py         (whole set)
#              python humaneval.py 40      (first 40 problems)

from __future__ import annotations

import ast
import collections
import sys

from mbpp import Vetter, edge_args, fuzz_args, build_reference

DATASET = "openai_humaneval"


def parse_asserts(test_source, entry_point):
    # Every `assert f(literals...) == literal` inside check(), where f is either
    # `candidate` or the entry point. Anything else is dropped.
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], ast.Eq):
            continue
        call = test.left
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        if call.func.id not in ("candidate", entry_point) or call.keywords:
            continue
        try:
            args = tuple(ast.literal_eval(a) for a in call.args)
            expected = ast.literal_eval(test.comparators[0])
        except (ValueError, SyntaxError):
            continue
        out.append((args, expected))
    return out


def make_tasks(limit=None, hidden=3, oracle=50, seed=0, min_visible=3):
    import random

    from datasets import load_dataset

    rng = random.Random(seed)
    tasks = []
    skipped = collections.Counter()
    vetter = Vetter()

    records = load_dataset(DATASET, split="test")

    for record in records:
        if limit is not None and len(tasks) >= limit:
            break

        name = record["entry_point"]
        parsed = parse_asserts(record["test"], name)
        if len(parsed) < min_visible:
            skipped["fewer than three parseable asserts"] += 1
            continue

        visible = [args for args, _ in parsed]
        # The prompt carries the imports, signature and docstring. The canonical
        # solution is only the body, so neither runs on its own.
        source = record["prompt"] + record["canonical_solution"]

        wanted = hidden + oracle
        candidates = []
        for _ in range(wanted * 4):
            if len(candidates) >= wanted:
                break
            args = fuzz_args(visible, rng)
            if args is not None and args not in visible:
                candidates.append(args)

        job = ("", source, name, parsed, candidates, edge_args(visible))
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
            reference = build_reference({"code": source, "test_setup_code": ""}, name)
        except Exception:
            skipped["reference will not import"] += 1
            continue

        tasks.append({
            "benchmark": "humaneval",
            "name": f"{name}_{record['task_id'].split('/')[-1]}",
            "reference": reference,
            "source": source,
            "func_name": name,
            "visible_tests": visible,
            "hidden_tests": kept[:hidden],
            "oracle_inputs": kept[hidden:] + kept_edges,
            "edge_tests": kept_edges,
            "description": record["prompt"],
        })

    vetter.close()
    print(f"{len(tasks)} usable tasks out of {len(records)} problems")
    for reason, count in skipped.most_common():
        print(f"  skipped {count:4d}  {reason}")
    return tasks


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ts = make_tasks(limit=limit)
    if ts:
        sizes = collections.Counter(len(t["visible_tests"]) for t in ts)
        print("\nvisible tests per problem:")
        for k in sorted(sizes):
            print(f"  {k:3d} tests -> {sizes[k]:3d} problems")
