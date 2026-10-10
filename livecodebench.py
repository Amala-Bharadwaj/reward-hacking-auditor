# Builds auditor tasks out of LiveCodeBench problems.
#
# The structural difference from MBPP is that LiveCodeBench ships no reference
# solution, so there is nothing to execute as ground truth and nothing to fuzz
# against. What it ships instead is a large private test set, 30 to 50 cases
# per problem, alongside a handful of public ones.
#
# That maps onto the auditor cleanly without any fuzzing at all:
#
#   visible_tests  = the public tests, which is what a solver is shown
#   hidden_tests   = a few private cases, standing in for a held-out suite
#   oracle_inputs  = the remaining private cases, used as ground truth
#   reference      = a lookup over every known input/output pair
#
# The reference is a table rather than a program, which is fine because it is
# only ever called on inputs that came from the dataset. auditor.py never
# invents an input of its own.
#
# Only functional-style problems are usable. Codeforces and AtCoder problems
# are graded on stdin/stdout, and a stdin program is not a callable, so those
# are counted and dropped. That skew is real and belongs in the paper: what
# survives is the LeetCode end of the benchmark.
#
# Fetch the data once with  python livecodebench.py --fetch
# then                      python livecodebench.py --limit 50

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

    # trust_remote_code is required by this dataset's loader script.
    return load_dataset(DATASET, version_tag=version, split="test",
                        trust_remote_code=True)


def decode_tests(blob):
    # Public tests are plain JSON. Private tests are zlib-compressed pickled
    # JSON behind base64, to keep them out of search indexes and out of
    # training data. Both shapes turn up, so try the cheap one first.
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
    # A functional case looks like {"input": "[1, 2]\n3", "output": "4",
    # "testtype": "functional"}. Each line of the input is one argument,
    # JSON encoded. Anything that will not parse is dropped rather than
    # guessed at.
    if case.get("testtype") != "functional":
        return None
    try:
        args = tuple(json.loads(line) for line in
                     str(case["input"]).strip().split("\n") if line.strip())
        expected = json.loads(str(case["output"]).strip())
    except (json.JSONDecodeError, KeyError):
        return None
    # Lists are unhashable, so the lookup key has to be repr based. Tuples of
    # lists are common here, which is why this is not a plain dict key.
    return args, expected


def build_reference(pairs, name):
    table = {repr(args): expected for args, expected in pairs}

    def reference(*args):
        key = repr(args)
        if key not in table:
            # Only reachable if something outside this module invents an input.
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
            # Almost always a stdin/stdout problem from Codeforces or AtCoder.
            skipped["no functional public tests"] += 1
            continue
        if len(private) < hidden + min_oracle:
            skipped["too few private tests"] += 1
            continue

        # A problem whose public and private cases disagree on the same input
        # cannot be used as ground truth, the same way an MBPP reference that
        # fails its own tests cannot.
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
            # No source to mutate, so attributes.py reports mutation_score None
            # for these and the regression treats it as missing.
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
