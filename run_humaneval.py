# Audits the published HumanEval test suites with the same attacks and the same
# verifiers used for MBPP. Runs the whole set unless you pass a smaller number.

import os
import sys

import pandas as pd

import plus_oracle
from attacks import all_attacks
from auditor import (audit, empty_verifier, strong_empty_verifier,
                     strong_verifier, targeted_verifier, weak_verifier)
from humaneval import make_tasks

VERIFIERS = [("weak", weak_verifier), ("strong", strong_verifier),
             ("weak_empty", empty_verifier),
             ("strong_empty", strong_empty_verifier),
             ("targeted", targeted_verifier)]


def main():
    os.makedirs("results", exist_ok=True)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    tasks = make_tasks(limit=limit)
    covered = plus_oracle.attach(tasks, "humaneval")
    print(f"{covered}/{len(tasks)} tasks carry an EvalPlus oracle")
    attacks = all_attacks()

    all_rows = []
    counts = {}
    for name, verifier in VERIFIERS:
        count, total, rows = audit(tasks, attacks, verifier)
        counts[name] = count, total
        for row in rows:
            row["verifier"] = name
        all_rows.extend(rows)

    weak_count, total = counts["weak"]
    strong_count, _ = counts["strong"]

    frame = pd.DataFrame(all_rows)
    frame.to_csv("results/humaneval_report.csv", index=False)

    by_attack = (frame.groupby(["attack", "verifier"])["false_accept"]
                 .mean()
                 .unstack()
                 .reindex(columns=[name for name, _ in VERIFIERS]))

    print()
    print("Share of tasks each attack false-accepts on")
    print(by_attack.round(3).to_string())
    print()
    print(f"Published tests only, false-accept rate  "
          f"{weak_count / total:.1%} ({weak_count}/{total})")
    print(f"Plus three held-out tests                "
          f"{strong_count / total:.1%} ({strong_count}/{total})")

    if "false_accept_plus" in frame:
        sub = frame.dropna(subset=["false_accept_plus"])
        print()
        print(f"EvalPlus oracle subset, {sub['task'].nunique()} tasks")
        print(sub.groupby(["attack", "verifier"])[["false_accept",
                                                   "false_accept_plus"]]
              .mean()
              .round(3)
              .to_string())
    print("Saved results/humaneval_report.csv")


if __name__ == "__main__":
    main()
