from __future__ import annotations

import ast
import copy
import json
import multiprocessing
import os
import sys

from auditor import call

COMPARE_SWAP = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
BINOP_SWAP = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
}


class _Mutator(ast.NodeTransformer):

    def __init__(self, target):
        self.target = target
        self.seen = 0

    def _hit(self):
        self.seen += 1
        return self.seen - 1 == self.target

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in COMPARE_SWAP and self._hit():
            node.ops = [COMPARE_SWAP[type(node.ops[0])]()]
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in BINOP_SWAP and self._hit():
            node.op = BINOP_SWAP[type(node.op)]()
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, bool) and self._hit():
            return ast.copy_location(ast.Constant(value=not node.value), node)
        if isinstance(node.value, int) and not isinstance(node.value, bool) and self._hit():
            return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node


def count_sites(source):
    counter = _Mutator(-1)
    counter.visit(ast.parse(source))
    return counter.seen


def make_mutant(source, index):
    tree = _Mutator(index).visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _mutation_job(job):
    source, name, visible, expected = job
    total = count_sites(source)
    if total == 0:
        return None
    killed = 0
    for i in range(total):
        try:
            namespace = {}
            exec(make_mutant(source, i), namespace)
            mutant = namespace[name]
        except Exception:
            killed += 1
            continue
        for args, want in zip(visible, expected):
            try:
                if mutant(*copy.deepcopy(args)) != want:
                    killed += 1
                    break
            except Exception:
                killed += 1
                break
    return killed / total


def _stub_job(job):
    _, _, visible, expected = job
    stubs = [lambda *a: None, lambda *a: 0, lambda *a: [],
             lambda *a: "", lambda *a: True]
    best = 0
    for stub in stubs:
        passed = sum(1 for args, want in zip(visible, expected)
                     if _safe_eq(stub, args, want))
        best = max(best, passed)
    return best / len(visible) if visible else 0.0


def _safe_eq(fn, args, want):
    try:
        return fn(*copy.deepcopy(args)) == want
    except Exception:
        return False


class Worker:

    def __init__(self, seconds=30):
        self.seconds = seconds
        self.pool = None

    def run(self, fn, job):
        if self.pool is None:
            self.pool = multiprocessing.Pool(1)
        try:
            return self.pool.apply_async(fn, (job,)).get(self.seconds)
        except multiprocessing.TimeoutError:
            self.pool.terminate()
            self.pool = None
            return None
        except Exception:
            return None

    def close(self):
        if self.pool is not None:
            self.pool.terminate()
            self.pool = None


def _shape(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, (list, tuple)):
        if any(isinstance(v, (list, tuple, dict)) for v in value):
            return "nested"
        return "flat_seq"
    return "other"


def input_type(visible):
    shapes = {_shape(v) for args in visible for v in args}
    if not shapes:
        return "none"
    order = ["nested", "dict", "flat_seq", "string", "number", "bool", "other"]
    for kind in order:
        if kind in shapes:
            return kind
    return "other"


def has_edge_case(visible):
    for args in visible:
        for v in args:
            if isinstance(v, str) and len(v) <= 1:
                return True
            if isinstance(v, (list, tuple, dict)) and len(v) <= 1:
                return True
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and v <= 0:
                return True
    return False


def input_diversity(visible):
    if not visible:
        return 0.0
    varied = 0
    for position in zip(*visible):
        if len({repr(v) for v in position}) > 1:
            varied += 1
    return varied / max(1, len(visible[0]))


def structural(task):
    visible = task["visible_tests"]
    return {
        "n_visible_tests": len(visible),
        "n_oracle_inputs": len(task["oracle_inputs"]),
        "input_type": input_type(visible),
        "has_edge_case": has_edge_case(visible),
        "input_diversity": round(input_diversity(visible), 3),
        "desc_words": len(task["description"].split()),
    }


def describe(task, worker):
    row = {"benchmark": task["benchmark"], "task": task["name"]}
    row.update(structural(task))

    expected = [call(task["reference"], args) for args in task["visible_tests"]]
    job = (task.get("source"), task.get("func_name"), task["visible_tests"], expected)

    row["dummy_pass_rate"] = round(_stub_job(job), 3)

    if job[0] is None:
        row["mutation_score"] = None
    else:
        score = worker.run(_mutation_job, job)
        row["mutation_score"] = None if score is None else round(score, 3)
    return row


def build(tasks):
    worker = Worker()
    rows = []
    for i, task in enumerate(tasks, 1):
        rows.append(describe(task, worker))
        if i % 50 == 0:
            print(f"  {i}/{len(tasks)} suites described")
    worker.close()
    return rows


def main():
    from mbpp import make_tasks

    os.makedirs("results", exist_ok=True)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    tasks = make_tasks(limit=limit)
    rows = build(tasks)

    path = "results/attributes.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    scored = [r["mutation_score"] for r in rows if r["mutation_score"] is not None]
    dummy = [r["dummy_pass_rate"] for r in rows]
    print()
    print(f"described {len(rows)} suites, wrote {path}")
    if scored:
        print(f"mean mutation score   {sum(scored) / len(scored):.3f}  "
              f"(computed for {len(scored)}/{len(rows)})")
    print(f"mean dummy pass rate  {sum(dummy) / len(dummy):.3f}")


if __name__ == "__main__":
    main()
