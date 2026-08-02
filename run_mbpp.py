# Audits the real published MBPP test suites.

import os

import matplotlib.pyplot as plt
import pandas as pd

from attacks import all_attacks
from auditor import audit, strong_verifier, weak_verifier
from mbpp import make_tasks

os.makedirs("results", exist_ok=True)
tasks = make_tasks(limit=100)
attacks = all_attacks()
print(f"Built {len(tasks)} usable MBPP tasks")

weak_count, total, weak_rows = audit(tasks, attacks, weak_verifier)
strong_count, _, strong_rows = audit(tasks, attacks, strong_verifier)

for row in weak_rows:
    row["verifier"] = "weak"
for row in strong_rows:
    row["verifier"] = "strong"

frame = pd.DataFrame(weak_rows + strong_rows)
frame.to_csv("results/mbpp_report.csv", index=False)

weak_rate = weak_count / total
strong_rate = strong_count / total

by_attack = (frame.groupby(["attack", "verifier"])["false_accept"]
             .mean()
             .unstack()
             .reindex(columns=["weak", "strong"]))

print()
print("Share of tasks each attack false-accepts on")
print(by_attack.round(2).to_string())
print()
print(f"Published MBPP tests only, false-accept rate  {weak_rate:.0%} ({weak_count}/{total})")
print(f"Plus three held-out tests, false-accept rate  {strong_rate:.0%} ({strong_count}/{total})")

by_attack.plot(kind="barh", color=["#c0392b", "#27ae60"])
plt.xlabel("Share of tasks false-accepted")
plt.title("Which cheats beat real MBPP test suites")
plt.xlim(0, 1)
plt.tight_layout()
plt.savefig("results/mbpp_false_accept_rates.png", dpi=120)
print("Saved results/mbpp_report.csv and results/mbpp_false_accept_rates.png")
