from __future__ import annotations

import ast
import copy
import functools
import json
import os
import sys

DATASETS = {
    "mbpp": "evalplus/mbppplus",
    "humaneval": "evalplus/humanevalplus",
}


def extract_inputs(test_source):
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "inputs" not in targets:
            continue
        try:
            values = ast.literal_eval(node.value)
        except (ValueError, SyntaxError, TypeError):
            return None
        return [tuple(args) for args in values]
    return None


def task_key(benchmark, raw_id):
    return str(raw_id).split("/")[-1]


def reference_source(benchmark, record):
    if benchmark == "humaneval":
        return record["prompt"] + record["canonical_solution"]
    return record["code"]


@functools.lru_cache(maxsize=None)
def plus_table(benchmark):
    from datasets import load_dataset

    records = load_dataset(DATASETS[benchmark], split="test")
    out = {}
    for record in records:
        inputs = extract_inputs(record["test"])
        if not inputs:
            continue
        out[task_key(benchmark, record["task_id"])] = {
            "inputs": inputs,
            "source": reference_source(benchmark, record),
        }
    return out


def plus_inputs(benchmark):
    return {k: v["inputs"] for k, v in plus_table(benchmark).items()}


CACHE = "results/plus_oracle_{}.jsonl"


def _filter_job(job):
    setup, source, name, inputs = job
    ns = {}
    exec(setup, ns)
    exec(source, ns)
    reference = ns[name]
    kept = []
    for args in inputs:
        try:
            reference(*copy.deepcopy(args))
        except Exception:
            continue
        kept.append(args)
    return kept


def build_cache(benchmark, tasks, setups=None):
    from attributes import Worker

    table = plus_table(benchmark)
    worker = Worker(seconds=120)
    written = kept_total = seen_total = 0
    os.makedirs("results", exist_ok=True)
    path = CACHE.format(benchmark)
    with open(path, "w", encoding="utf-8") as f:
        for task in tasks:
            entry = table.get(task["name"].rsplit("_", 1)[-1])
            if entry is None:
                continue
            setup = (setups or {}).get(task["name"].rsplit("_", 1)[-1], "")
            inputs = entry["inputs"]
            kept = worker.run(_filter_job,
                              (setup, task["source"], task["func_name"],
                               inputs))
            if not kept:
                continue
            seen_total += len(inputs)
            kept_total += len(kept)
            f.write(json.dumps({"task": task["name"], "inputs": repr(kept)}) + "\n")
            written += 1
    worker.close()
    print(f"{benchmark}: cached {written} tasks, "
          f"{kept_total}/{seen_total} inputs survive the reference "
          f"({kept_total / max(1, seen_total):.1%}), wrote {path}")
    return path


def load_cache(benchmark):
    path = CACHE.format(benchmark)
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            out[row["task"]] = ast.literal_eval(row["inputs"])
    return out


def attach(tasks, benchmark):
    cache = load_cache(benchmark)
    hit = 0
    for task in tasks:
        inputs = cache.get(task["name"])
        if inputs:
            task["plus_oracle"] = inputs
            hit += 1
    return hit


def mbpp_setups():
    setups = {}
    with open("data_mbpp.jsonl", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            setups[str(record["task_id"])] = record.get("test_setup_code") or ""
    return setups


def main():
    benchmark = sys.argv[1] if len(sys.argv) > 1 else "mbpp"
    if benchmark == "mbpp":
        from mbpp import make_tasks
        build_cache(benchmark, make_tasks(), mbpp_setups())
    else:
        from humaneval import make_tasks
        build_cache(benchmark, make_tasks())


if __name__ == "__main__":
    main()
