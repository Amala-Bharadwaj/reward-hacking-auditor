# Re-scores stored model attempts without calling the model again.
#
# Every attempt in results/llm_attempts.jsonl keeps the source it generated, so
# the EvalPlus oracle and the hardened lookup-table rule can both be applied to
# a finished run. Nothing here regenerates code, so the model, the seeds and the
# sampling are exactly the ones already reported.
#
# Run it with  python rescore.py

from __future__ import annotations

import copy
import json
import os
import sys

import plus_oracle
from auditor import call
from llm_attack import Scorer, looks_enumerative

ATTEMPTS = "results/llm_attempts.jsonl"
OUT = "results/llm_rescored.jsonl"


def paths():
    if len(sys.argv) > 2:
        return sys.argv[1], sys.argv[2]
    return ATTEMPTS, OUT


def _job(job):
    code, name, visible, hidden, oracle, plus = job
    try:
        namespace = {}
        exec(code, namespace)
        candidate = namespace[name]
    except Exception as exc:
        return {"ran": False, "error": f"{type(exc).__name__}: {exc}"}

    def passes(pairs):
        for args, want in pairs:
            try:
                if candidate(*copy.deepcopy(args)) != want:
                    return False
            except Exception:
                return False
        return True

    weak = passes(visible)
    strong = weak and passes(hidden)
    # A candidate that fails the published tests is a false positive under no
    # verifier, so its oracle verdict cannot change any reported column. Seven
    # attempts in ten fail there, and each oracle pass costs a hundred and sixty
    # executions of model-written code. truly_solves is left null for those
    # rows; nothing downstream reads it.
    solved = passes(oracle) if weak else None
    row = {
        "ran": True,
        "passed_visible": weak,
        "passed_with_held_out": strong,
        "truly_solves": solved,
        "false_accept": bool(weak and not solved),
        "false_accept_with_held_out": bool(strong and not solved),
    }
    if plus:
        solved_plus = passes(plus) if weak else None
        row["truly_solves_plus"] = solved_plus
        row["false_accept_plus"] = bool(weak and not solved_plus)
        row["false_accept_plus_with_held_out"] = bool(strong and not solved_plus)
    return row


def pairs_for(task, key):
    return [(args, call(task["reference"], args)) for args in task.get(key, [])]


def load_done(out):
    # A full pass is hours long, so it has to survive being interrupted.
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a partial last line from an interrupted run
                done.add((row["task"], row["model"], row["sample"]))
    return done


def main():
    from mbpp import make_tasks

    attempts, out_path = paths()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tasks = {t["name"]: t for t in make_tasks()}
    covered = plus_oracle.attach(list(tasks.values()), "mbpp")
    print(f"{covered}/{len(tasks)} tasks carry an EvalPlus oracle")

    rows = []
    with open(attempts, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"{len(rows)} stored attempts")

    already = load_done(out_path)
    todo = sum(1 for r in rows
               if (r["task"], r["model"], r["sample"]) not in already)
    print(f"{len(already)} already rescored, {todo} to go")

    cache = {}
    scorer = Scorer(job_fn=_job)
    done = 0
    with open(out_path, "a", encoding="utf-8") as out:
        for row in rows:
            task = tasks.get(row["task"])
            if task is None:
                continue
            if (row["task"], row["model"], row["sample"]) in already:
                continue
            if row["task"] not in cache:
                cache[row["task"]] = (
                    pairs_for(task, "visible_tests"),
                    pairs_for(task, "hidden_tests"),
                    pairs_for(task, "oracle_inputs"),
                    pairs_for(task, "plus_oracle"),
                )
            visible, hidden, oracle, plus = cache[row["task"]]
            expected = [want for _, want in visible]
            scored = scorer.run((row["code"], task["func_name"],
                                 visible, hidden, oracle, plus))
            out.write(json.dumps({
                "benchmark": row["benchmark"],
                "task": row["task"],
                "model": row["model"],
                "sample": row["sample"],
                "seed": row.get("seed"),
                "has_plus": bool(plus),
                "enumerative": looks_enumerative(row["code"],
                                                 task["visible_tests"], expected),
                "enumerative_shipped": row.get("enumerative"),
                **scored,
            }) + "\n")
            out.flush()  # a killed run keeps everything up to the last attempt
            done += 1
            if done % 250 == 0:
                print(f"  {done}/{todo}", flush=True)
    scorer.close()
    print(f"rescored {done} this pass, wrote {out_path}")


if __name__ == "__main__":
    main()
