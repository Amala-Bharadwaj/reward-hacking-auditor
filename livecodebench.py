from __future__ import annotations

import argparse
import base64
import collections
import json
import pickle
import zlib

DATASET = "livecodebench/code_generation_lite"
VERSION = "release_v6"


def fetch(version=VERSION):
    from datasets import load_dataset

    return load_dataset(DATASET, version_tag=version, split="test",
                        trust_remote_code=True)


def decode_tests(blob):
    if not blob:
        return []
    if isinstance(blob, list):
        return blob
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return json.loads(pickle.loads(zlib.decompress(base64.b64decode(blob))))
    except Exception:
        return []


def parse_case(case):
    if case.get("testtype") != "functional":
        return None
    try:
        args = tuple(json.loads(line) for line in
                     str(case["input"]).strip().split("\n") if line.strip())
        expected = json.loads(str(case["output"]).strip())
    except (json.JSONDecodeError, KeyError):
        return None
    return args, expected


def build_reference(pairs, name):
    table = {repr(args): expected for args, expected in pairs}

    def reference(*args):
        key = repr(args)
        if key not in table:
            raise KeyError(f"{name}: no ground truth for {key}")
        return table[key]

    return reference


def make_tasks(limit=None, hidden=3, min_oracle=10, version=VERSION):
    dataset = fetch(version)
    tasks = []
    skipped = collections.Counter()

    for record in dataset:
        if limit is not None and len(tasks) >= limit:
            break

        public = [parse_case(c) for c in decode_tests(record.get("public_test_cases"))]
        private = [parse_case(c) for c in decode_tests(record.get("private_test_cases"))]
        public = [p for p in public if p is not None]
        private = [p for p in private if p is not None]

        if not public:
            skipped["no functional public tests"] += 1
            continue
        if len(private) < hidden + min_oracle:
            skipped["too few private tests"] += 1
            continue

        table = {}
        conflict = False
        for args, expected in public + private:
            key = repr(args)
            if key in table and table[key] != expected:
                conflict = True
                break
            table[key] = expected
        if conflict:
            skipped["public and private tests disagree"] += 1
            continue

        name = f"lcb_{record.get('question_id', len(tasks))}"
        tasks.append({
            "benchmark": "livecodebench",
            "name": name,
            "reference": build_reference(public + private, name),
            "source": None,
            "func_name": name,
            "visible_tests": [args for args, _ in public],
            "hidden_tests": [args for args, _ in private[:hidden]],
            "oracle_inputs": [args for args, _ in private[hidden:]],
            "description": record.get("question_content", ""),
            "difficulty": record.get("difficulty"),
            "platform": record.get("platform"),
        })

    print(f"{len(tasks)} usable tasks out of {len(dataset)} problems")
    for reason, count in skipped.most_common():
        print(f"  skipped {count:4d}  {reason}")
    return tasks


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fetch", action="store_true", help="download and cache only")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--version", default=VERSION)
    args = p.parse_args()

    if args.fetch:
        dataset = fetch(args.version)
        print(f"cached {len(dataset)} problems from {DATASET} {args.version}")
        print("columns:", dataset.column_names)
        raise SystemExit

    tasks = make_tasks(limit=args.limit, version=args.version)
    if tasks:
        t = tasks[0]
        print()
        print(f"example: {t['name']}  {t['platform']}  {t['difficulty']}")
        print(f"  visible {len(t['visible_tests'])}  hidden {len(t['hidden_tests'])}"
              f"  oracle {len(t['oracle_inputs'])}")
