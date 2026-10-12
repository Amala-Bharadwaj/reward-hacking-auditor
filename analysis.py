from __future__ import annotations

import json
import math
import os

import pandas as pd

ATTRIBUTES = "results/attributes.jsonl"
ATTEMPTS = "results/llm_attempts.jsonl"


def read_jsonl(path):
    if not os.path.exists(path):
        raise SystemExit(f"{path} is missing. Generate it first.")
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return pd.DataFrame(rows)


def wilson(successes, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def benjamini_hochberg(pvalues):
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    out = {}
    running = 1.0
    for rank in range(m, 0, -1):
        term, p = ordered[rank - 1]
        running = min(running, p * m / rank)
        out[term] = min(1.0, running)
    return out


def per_task(attempts):
    ran = attempts[attempts["ran"]]
    spec = dict(
        attempts_ran=("false_accept", "size"),
        n_gamed=("false_accept", "sum"),
        n_gamed_held_out=("false_accept_with_held_out", "sum"),
    )
    for column, alias in (("false_accept_plus", "n_gamed_plus"),
                          ("false_accept_plus_with_held_out",
                           "n_gamed_plus_held_out")):
        if column in ran:
            spec[alias] = (column, "sum")
    grouped = ran.groupby(["benchmark", "task"]).agg(**spec).reset_index()
    grouped["exploited"] = grouped["n_gamed"] > 0
    grouped["exploited_defended"] = grouped["n_gamed_held_out"] > 0
    for alias, outcome in (("n_gamed_plus", "exploited_plus"),
                           ("n_gamed_plus_held_out", "exploited_plus_defended")):
        if alias in grouped:
            grouped[outcome] = grouped[alias] > 0
    grouped["exploit_rate"] = grouped["n_gamed"] / grouped["attempts_ran"]
    return grouped


def headline(attempts, tasks, out):
    ran = attempts[attempts["ran"]]
    n = len(ran)
    gamed = int(ran["false_accept"].sum())
    held = int(ran["false_accept_with_held_out"].sum())
    lo, hi = wilson(gamed, n)
    hlo, hhi = wilson(held, n)
    exploited = int(tasks["exploited"].sum())
    elo, ehi = wilson(exploited, len(tasks))

    out.append(f"attempts that compiled and ran   {n}/{len(attempts)}")
    out.append(f"per-attempt false-accept rate    {gamed / n:.1%}  "
               f"[{lo:.1%}, {hi:.1%}]")
    out.append(f"  with held-out tests added      {held / n:.1%}  "
               f"[{hlo:.1%}, {hhi:.1%}]")
    out.append(f"tasks ever exploited             {exploited}/{len(tasks)} "
               f"= {exploited / len(tasks):.1%}  [{elo:.1%}, {ehi:.1%}]")
    if gamed:
        out.append(f"  held-out tests remove          "
                   f"{1 - held / gamed:.1%} of successful attacks")


def by_group(frame, column, out, min_n=15):
    out.append("")
    out.append(f"exploitation rate by {column}")
    grouped = frame.groupby(column)["exploited"].agg(["size", "sum"])
    for value, row in grouped.sort_values("size", ascending=False).iterrows():
        n, k = int(row["size"]), int(row["sum"])
        lo, hi = wilson(k, n)
        flag = "" if n >= min_n else "   (n too small)"
        out.append(f"  {str(value):<12} {k:4d}/{n:<4d} = {k / n:6.1%}  "
                   f"[{lo:.1%}, {hi:.1%}]{flag}")


def by_bucket(frame, column, out, bins=4):
    usable = frame[frame[column].notna()]
    if len(usable) < bins * 10 or usable[column].nunique() < bins:
        out.append("")
        out.append(f"exploitation rate by {column}: too few values to bucket")
        return
    labelled = usable.copy()
    labelled["bucket"] = pd.qcut(labelled[column], bins, duplicates="drop")
    out.append("")
    out.append(f"exploitation rate by {column} (quartiles)")
    for value, group in labelled.groupby("bucket", observed=True):
        n, k = len(group), int(group["exploited"].sum())
        lo, hi = wilson(k, n)
        out.append(f"  {str(value):<20} {k:4d}/{n:<4d} = {k / n:6.1%}  "
                   f"[{lo:.1%}, {hi:.1%}]")


def regression(frame, out, outcome="exploited", with_mutation=True):
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        out.append("")
        out.append("statsmodels not installed, skipping regression "
                   "(pip install statsmodels)")
        return

    if outcome not in frame:
        return
    needed = ["dummy_pass_rate", "n_visible_tests", "input_diversity"]
    if with_mutation:
        needed.append("mutation_score")
    usable = frame.dropna(subset=needed)
    label = (f"outcome={outcome}, "
             f"{'with' if with_mutation else 'without'} mutation_score")
    if len(usable) < 50 or usable[outcome].nunique() < 2:
        out.append("")
        out.append(f"{label}: not enough variation for a regression")
        return

    terms = ["dummy_pass_rate", "n_visible_tests",
             "input_diversity", "has_edge_case", "input_type", "benchmark"]
    if with_mutation:
        terms.insert(0, "mutation_score")
    varying = [t for t in terms if usable[t].nunique() > 1]
    dropped = [t for t in terms if t not in varying]
    formula = f"{outcome} ~ " + " + ".join(
        f"C({t})" if t in ("input_type", "benchmark") else t for t in varying)

    model = smf.logit(formula, data=usable.assign(
        **{outcome: usable[outcome].astype(int)})).fit(disp=False)
    out.append("")
    out.append(f"logistic regression, {label}, n={len(usable)}, "
               f"{int(usable[outcome].sum())} positives")
    if dropped:
        out.append(f"  dropped, no variation in this corpus: {', '.join(dropped)}")
    out.append("  odds ratios, 95% CI, p")
    params, conf = model.params, model.conf_int()

    def odds(x):
        try:
            return f"{math.exp(x):.3f}"
        except OverflowError:
            return "inf"

    tested = [t for t in params.index if t != "Intercept"]
    adjusted = benjamini_hochberg({t: model.pvalues[t] for t in tested})
    for term in tested:
        out.append(f"  {term:<34} {odds(params[term]):>7}  "
                   f"[{odds(conf.loc[term, 0])}, {odds(conf.loc[term, 1])}]  "
                   f"p={model.pvalues[term]:.4f}  "
                   f"BH={adjusted[term]:.4f}")


def main():
    import sys

    attempts = read_jsonl(sys.argv[1] if len(sys.argv) > 1 else ATTEMPTS)
    attributes = read_jsonl(ATTRIBUTES)

    tasks = per_task(attempts)
    frame = tasks.merge(attributes, on=["benchmark", "task"], how="inner")
    if frame.empty:
        raise SystemExit("no tasks in common between the two files. "
                         "Run attributes.py and llm_attack.py over the same set.")

    out = [f"tasks with both attacks and attributes: {len(frame)}", ""]
    headline(attempts, tasks, out)

    if frame["benchmark"].nunique() > 1:
        by_group(frame, "benchmark", out)
    by_group(frame, "input_type", out)
    by_group(frame, "has_edge_case", out)
    by_group(frame, "n_visible_tests", out)
    by_bucket(frame, "mutation_score", out)
    by_bucket(frame, "dummy_pass_rate", out)
    by_bucket(frame, "input_diversity", out)

    outcomes = ["exploited", "exploited_defended"]
    outcomes += [c for c in ("exploited_plus", "exploited_plus_defended")
                 if c in frame]
    for outcome in outcomes:
        for with_mutation in (False, True):
            regression(frame, out, outcome=outcome, with_mutation=with_mutation)

    text = "\n".join(out)
    print(text)
    with open("results/analysis.txt", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print("\nwrote results/analysis.txt")


if __name__ == "__main__":
    main()
