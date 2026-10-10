# Classifies each model-written false positive by which region of the oracle it
# actually fails on.
#
# The constructed probes in Section 3.1 are defined to be wrong on a chosen
# region, which makes them a hypothesis about where search goes rather than
# evidence for it. This partitions real model failures over the same regions, so
# the probes can be checked against the failure distribution instead of assumed.
#
# Run it with  python failure_modes.py

from __future__ import annotations

import collections
import copy
import json
import os
import sys

from attacks import _envelope, _numbers
from auditor import call
from llm_attack import Scorer

RESCORED = "results/llm_rescored.jsonl"
ATTEMPTS = "results/llm_attempts.jsonl"
OUT = "results/failure_modes.json"


def paths():
    if len(sys.argv) > 3:
        return sys.argv[1], sys.argv[2], sys.argv[3]
    return RESCORED, ATTEMPTS, OUT


def region(args, bounds):
    for value in args:
        if isinstance(value, (list, tuple, str, dict)) and len(value) == 0:
            return "empty"
    for value in args:
        if isinstance(value, int) and not isinstance(value, bool) and value == 0:
            return "zero"
    if bounds is not None:
        for value in args:
            for n in _numbers(value):
                if n < bounds[0] or n > bounds[1]:
                    return "outside"
    return "inside"


def _job(job):
    code, name, pairs = job
    try:
        namespace = {}
        exec(code, namespace)
        candidate = namespace[name]
    except Exception:
        return None
    failed = []
    for i, (args, want) in enumerate(pairs):
        try:
            if candidate(*copy.deepcopy(args)) != want:
                failed.append(i)
        except Exception:
            failed.append(i)
    return failed


def classify(failed_regions):
    # Precedence runs from the most specific region outwards. A candidate that
    # is ever wrong on an ordinary input is reported as such whatever else it
    # also fails, because that is the failure the published tests could have
    # caught.
    if "inside" in failed_regions:
        return "wrong on ordinary inputs"
    if failed_regions <= {"empty", "zero"}:
        return "empty or zero only"
    if failed_regions == {"outside"}:
        return "outside published range only"
    return "mixed edge regions"


def main():
    from mbpp import make_tasks

    rescored, attempts, out_path = paths()
    tasks = {t["name"]: t for t in make_tasks()}
    rows = []
    with open(rescored, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # The re-scored file carries verdicts, not source, so the code comes from the
    # original attempts keyed the same way.
    codes = {}
    with open(attempts, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            codes[(r["task"], r["model"], r["sample"])] = r["code"]

    cache = {}
    scorer = Scorer(job_fn=_job)
    counts = collections.Counter()
    counts_held = collections.Counter()
    region_hits = collections.Counter()
    unclassified = 0
    per_row = []

    targets = [r for r in rows if r.get("ran") and r.get("false_accept")]
    print(f"{len(targets)} false positives to classify")

    for n, row in enumerate(targets, 1):
        task = tasks.get(row["task"])
        code = codes.get((row["task"], row["model"], row["sample"]))
        if task is None or code is None:
            continue
        if row["task"] not in cache:
            bounds = _envelope(task)
            pairs = [(a, call(task["reference"], a)) for a in task["oracle_inputs"]]
            cache[row["task"]] = (pairs, [region(a, bounds) for a, _ in pairs])
        pairs, regions = cache[row["task"]]
        failed = scorer.run((code, task["func_name"], pairs))
        # Scorer reports a timeout or a crashed pool as a dict, not a list of
        # failing indices, and a candidate that will not import comes back None.
        if not isinstance(failed, list) or not failed:
            unclassified += 1
            continue
        hit = {regions[i] for i in failed}
        label = classify(hit)
        counts[label] += 1
        for r in hit:
            region_hits[r] += 1
        if row.get("false_accept_with_held_out"):
            counts_held[label] += 1
        per_row.append({"task": row["task"], "sample": row["sample"],
                        "label": label, "regions": sorted(hit),
                        "enumerative": row.get("enumerative"),
                        "held_out": bool(row.get("false_accept_with_held_out"))})
        if n % 200 == 0:
            print(f"  {n}/{len(targets)}", flush=True)
    scorer.close()

    total = sum(counts.values())
    print(f"\nclassified {total}, could not reproduce a failure for {unclassified}")
    print("\nfalse positives against the published tests")
    for label, k in counts.most_common():
        print(f"  {label:32s} {k:5d}  {k/total:6.1%}")
    th = sum(counts_held.values())
    print(f"\nof those, the {th} that also survive the held-out tests")
    for label, k in counts_held.most_common():
        print(f"  {label:32s} {k:5d}  {k/th:6.1%}")
    print("\nregions touched, non-exclusive")
    for r, k in region_hits.most_common():
        print(f"  {r:32s} {k:5d}  {k/total:6.1%}")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(per_row, open(out_path, "w", encoding="utf-8"))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
