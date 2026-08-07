# A test is an argument tuple. The expected output is whatever the reference
# returns for it, so the visible, hidden and oracle sets can never disagree.

import copy


def call(fn, args):
    # Some MBPP reference solutions mutate the list they are given, so a second
    # call on the same input returns something different or raises. Every call
    # gets its own copy of the arguments.
    return fn(*copy.deepcopy(args))


def matches(candidate, reference, tests):
    for args in tests:
        try:
            if call(candidate, args) != call(reference, args):
                return False
        except Exception:
            return False
    return True


def weak_verifier(task, candidate):
    return matches(candidate, task["reference"], task["visible_tests"])


def strong_verifier(task, candidate):
    return matches(candidate, task["reference"],
                   task["visible_tests"] + task["hidden_tests"])


def truly_solves(task, candidate):
    return matches(candidate, task["reference"], task["oracle_inputs"])


def audit(tasks, attacks, verifier):
    # Run every attack against every task and record which ones fooled the verifier.
    rows = []
    for task in tasks:
        for name, attack in attacks.items():
            try:
                candidate = attack(task)
            except Exception:
                continue
            passed = verifier(task, candidate)
            solved = truly_solves(task, candidate)
            rows.append({
                "task": task["name"],
                "attack": name,
                "passed_verifier": passed,
                "truly_solves": solved,
                "false_accept": passed and not solved,
            })
    false_accepts = sum(r["false_accept"] for r in rows)
    return false_accepts, len(rows), rows
