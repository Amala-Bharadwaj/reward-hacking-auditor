import os

import matplotlib.pyplot as plt
import pandas as pd

from attacks import all_attacks
from auditor import audit, strong_verifier, weak_verifier
from tasks import make_tasks

os.makedirs("results", exist_ok=True)
tasks = make_tasks()
attacks = all_attacks()

weak_count, total, weak_rows = audit(tasks, attacks, weak_verifier)
strong_count, _, strong_rows = audit(tasks, attacks, strong_verifier)

for row in weak_rows:
    row["verifier"] = "weak"
for row in strong_rows:
    row["verifier"] = "strong"

pd.DataFrame(weak_rows + strong_rows).to_csv("results/report.csv", index=False)

weak_rate = weak_count / total
strong_rate = strong_count / total

print()
print("False accepts against the weak verifier")
print(pd.DataFrame(weak_rows)
      .pivot(index="attack", columns="task", values="false_accept")
      .to_string())
print()
print(f"Weak verifier false-accept rate   {weak_rate:.0%} ({weak_count}/{total})")
print(f"Strong verifier false-accept rate {strong_rate:.0%} ({strong_count}/{total})")

plt.bar(["weak (visible only)", "strong (visible and hidden)"],
        [weak_rate, strong_rate], color=["#c0392b", "#27ae60"])
plt.ylabel("False-accept rate")
plt.title("How gameable is the reward?")
plt.ylim(0, 1)
plt.tight_layout()
plt.savefig("results/false_accept_rates.png", dpi=120)
print("Saved results/report.csv and results/false_accept_rates.png")
