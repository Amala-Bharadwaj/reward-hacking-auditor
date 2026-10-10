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


def targeted_verifier(task, candidate):
    return matches(candidate, task["reference"],
                   task["visible_tests"] + task["hidden_tests"]
                   + task["edge_tests"])


def empty_tests(task):
    return [args for args in task["edge_tests"]
            if any(isinstance(v, (list, tuple, str, dict)) and len(v) == 0
                   for v in args)]


def empty_verifier(task, candidate):
    return matches(candidate, task["reference"],
                   task["visible_tests"] + empty_tests(task))


def strong_empty_verifier(task, candidate):
    return matches(candidate, task["reference"],
                   task["visible_tests"] + task["hidden_tests"]
                   + empty_tests(task))


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
            row = {
                "task": task["name"],
                "attack": name,
                "passed_verifier": passed,
                "truly_solves": solved,
                "false_accept": passed and not solved,
            }
            if task.get("plus_oracle"):
                # Same reference, EvalPlus inputs instead of fuzzed ones, so
                # the columns differ only in where the inputs came from.
                solved_plus = matches(candidate, task["reference"],
                                      task["plus_oracle"])
                row["truly_solves_plus"] = solved_plus
                row["false_accept_plus"] = passed and not solved_plus
            rows.append(row)
    false_accepts = sum(r["false_accept"] for r in rows)
    return false_accepts, len(rows), rows
