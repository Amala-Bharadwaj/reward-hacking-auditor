# Audits the real published MBPP test suites. Runs the whole dataset unless you
# pass a smaller number, for example  python run_mbpp.py 100

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import plus_oracle
from attacks import all_attacks
from auditor import (audit, empty_verifier, strong_empty_verifier,
                     strong_verifier, targeted_verifier, weak_verifier)
from mbpp import make_tasks

VERIFIERS = [("weak", weak_verifier), ("strong", strong_verifier),
             ("weak_empty", empty_verifier),
             ("strong_empty", strong_empty_verifier),
             ("targeted", targeted_verifier)]


def main():
    os.makedirs("results", exist_ok=True)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    tasks = make_tasks(limit=limit)
    covered = plus_oracle.attach(tasks, "mbpp")
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
    frame.to_csv("results/mbpp_report.csv", index=False)

    by_attack = (frame.groupby(["attack", "verifier"])["false_accept"]
                 .mean()
                 .unstack()
                 .reindex(columns=[name for name, _ in VERIFIERS]))

    print()
    print("Share of tasks each attack false-accepts on")
    print(by_attack.round(3).to_string())
    print()
    print(f"Published MBPP tests only, false-accept rate  "
          f"{weak_count / total:.0%} ({weak_count}/{total})")
    print(f"Plus three held-out tests, false-accept rate  "
          f"{strong_count / total:.0%} ({strong_count}/{total})")

    if "false_accept_plus" in frame:
        sub = frame.dropna(subset=["false_accept_plus"])
        print()
        print(f"EvalPlus oracle subset, {sub['task'].nunique()} tasks")
        print(sub.groupby(["attack", "verifier"])[["false_accept",
                                                   "false_accept_plus"]]
              .mean()
              .round(3)
              .to_string())

    by_attack.plot(kind="barh", color=["#c0392b", "#27ae60"])
    plt.xlabel("Share of tasks false-accepted")
    plt.title(f"Which cheats beat real MBPP test suites, {len(tasks)} problems")
    plt.xlim(0, 1)
    plt.tight_layout()
    plt.savefig("results/mbpp_false_accept_rates.png", dpi=120)
    print("Saved results/mbpp_report.csv and results/mbpp_false_accept_rates.png")


if __name__ == "__main__":
    main()
