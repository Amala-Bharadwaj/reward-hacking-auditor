# Runs the model-attack generation on Modal instead of the laptop.
#
# Each model gets its own container and its own attempts file. Four containers
# writing one file is what corrupted the local run, and separate files also make
# resume per model independent. They are merged after the fact.
#
#   python -m modal run modal_run.py::pull      one time, fills the model volume
#   python -m modal run modal_run.py::verify    determinism check on Modal's GPU
#   python -m modal run modal_run.py::launch    the real run, four in parallel

import modal

MODELS = [
    "qwen2.5-coder:1.5b",
    "qwen2.5-coder:3b",
    "qwen2.5-coder:7b",
    "deepseek-coder:6.7b-instruct",
]

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl", "zstd")
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
    .pip_install("openai==1.109.1")
    .env({"OLLAMA_MODELS": "/models", "PYTHONHASHSEED": "0"})
    .add_local_file("llm_attack.py", "/work/llm_attack.py", copy=True)
    .add_local_file("auditor.py", "/work/auditor.py", copy=True)
    .add_local_file("mbpp.py", "/work/mbpp.py", copy=True)
    .add_local_file("data_mbpp.jsonl", "/work/data_mbpp.jsonl", copy=True)
    .add_local_file("plus_oracle.py", "/work/plus_oracle.py", copy=True)
    .add_local_file("rescore.py", "/work/rescore.py", copy=True)
    .add_local_file("failure_modes.py", "/work/failure_modes.py", copy=True)
    .add_local_file("attacks.py", "/work/attacks.py", copy=True)
    .add_local_file("attributes.py", "/work/attributes.py", copy=True)
    .add_local_file("results/plus_oracle_mbpp.jsonl",
                    "/work/results/plus_oracle_mbpp.jsonl", copy=True)
)

app = modal.App("reward-hacking-audit", image=image)
model_vol = modal.Volume.from_name("ollama-models", create_if_missing=True)
results_vol = modal.Volume.from_name("audit-results", create_if_missing=True)


def serve_ollama():
    import subprocess
    import time
    import urllib.request

    subprocess.Popen(["ollama", "serve"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("ollama did not come up")


@app.function(volumes={"/models": model_vol}, timeout=60 * 60)
def pull():
    import subprocess

    serve_ollama()
    for name in MODELS:
        print(f"pulling {name}", flush=True)
        # Output is captured rather than streamed. Ollama's progress bar emits
        # thousands of redraw lines, which floods the client log.
        r = subprocess.run(["ollama", "pull", name],
                           capture_output=True, text=True)
        print(f"  exit {r.returncode} {r.stderr.strip()[-200:]}", flush=True)
        model_vol.commit()
    print(subprocess.run(["ollama", "list"], capture_output=True,
                         text=True).stdout, flush=True)


def _run(model, samples, limit, attempts_path):
    import os
    import sys

    os.chdir("/work")
    sys.path.insert(0, "/work")
    serve_ollama()

    import llm_attack as LA

    LA.ATTEMPTS = attempts_path
    LA.PROVIDERS["qwen"]["model"] = model
    sys.argv = ["llm_attack.py", "--model", "qwen", "--local-model", model,
                "--limit", str(limit), "--samples", str(samples)]
    LA.main()


@app.function(volumes={"/models": model_vol, "/results": results_vol},
              gpu="A10G", timeout=60 * 60 * 8)
def run_model(model: str, samples: int = 10, limit: int = 0):
    import os
    import threading

    tag = model.replace(":", "_").replace(".", "_")
    path = f"/results/attempts_{tag}.jsonl"

    # Committed on a timer, not only at the end. A container that dies at hour
    # three would otherwise lose everything, and llm_attack resumes from whatever
    # is on the volume.
    stop = threading.Event()

    def checkpoint():
        while not stop.wait(300):
            try:
                results_vol.commit()
            except Exception as exc:
                print(f"checkpoint failed: {type(exc).__name__}", flush=True)

    keeper = threading.Thread(target=checkpoint, daemon=True)
    keeper.start()
    try:
        _run(model, samples, limit, path)
    finally:
        stop.set()
        results_vol.commit()

    n = sum(1 for _ in open(path, encoding="utf-8")) if os.path.exists(path) else 0
    print(f"{model} wrote {n} attempts to {path}")
    return model, n


@app.function(volumes={"/models": model_vol}, gpu="A10G", timeout=60 * 60 * 2)
def verify(model: str = "qwen2.5-coder:1.5b", evictor: str = "qwen2.5-coder:7b"):
    # Everything verified locally was verified on a 4060. Different silicon means
    # different numerics, so the determinism check has to be repeated here before
    # the real run spends any credits.
    import json
    import os
    import sys

    def load(p):
        out = {}
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out[(r["task"], r["sample"])] = r["code"]
        return out

    a, b = "/tmp/a.jsonl", "/tmp/b.jsonl"
    for p in (a, b):
        if os.path.exists(p):
            os.remove(p)

    _run(model, 3, 20, a)

    sys.path.insert(0, "/work")
    import llm_attack as LA
    LA.PROVIDERS["qwen"]["model"] = evictor
    client = LA.make_client("qwen")
    from mbpp import make_tasks
    t = next(iter(make_tasks(limit=2)))
    try:
        LA.generate(client, "qwen", t, 5, 0.8)
    except Exception as exc:
        print("evictor call failed", exc)

    _run(model, 3, 20, b)

    A, B = load(a), load(b)
    keys = set(A) & set(B)
    same = sum(1 for k in keys if A[k] == B[k])
    print(f"byte-identical {same}/{len(keys)}")
    for k in sorted(keys):
        if A[k] != B[k]:
            print(f"  differs {k}")
    return same, len(keys)


@app.function(volumes={"/results": results_vol}, timeout=60 * 60 * 12)
def rescore_model(model: str):
    import os
    import sys
    import threading

    tag = model.replace(":", "_").replace(".", "_")
    os.chdir("/work")
    sys.path.insert(0, "/work")

    stop = threading.Event()

    def checkpoint():
        while not stop.wait(300):
            try:
                results_vol.commit()
            except Exception as exc:
                print(f"checkpoint failed: {type(exc).__name__}", flush=True)

    threading.Thread(target=checkpoint, daemon=True).start()
    sys.argv = ["rescore.py", f"/results/attempts_{tag}.jsonl",
                f"/results/rescored_{tag}.jsonl"]
    import rescore
    try:
        rescore.main()
    finally:
        stop.set()
        results_vol.commit()
    return model


@app.function(volumes={"/results": results_vol}, timeout=60 * 60 * 12)
def modes_model(model: str):
    import os
    import sys
    import threading

    tag = model.replace(":", "_").replace(".", "_")
    os.chdir("/work")
    sys.path.insert(0, "/work")

    stop = threading.Event()

    def checkpoint():
        while not stop.wait(300):
            try:
                results_vol.commit()
            except Exception as exc:
                print(f"checkpoint failed: {type(exc).__name__}", flush=True)

    threading.Thread(target=checkpoint, daemon=True).start()
    sys.argv = ["failure_modes.py",
                f"/results/rescored_{tag}.jsonl",
                f"/results/attempts_{tag}.jsonl",
                f"/results/modes_{tag}.json"]
    import failure_modes
    try:
        failure_modes.main()
    finally:
        stop.set()
        results_vol.commit()
    return model


@app.local_entrypoint()
def rescore_all():
    for model in rescore_model.map(MODELS):
        print(f"rescored {model}")


@app.local_entrypoint()
def launch(samples: int = 10, limit: int = 0):
    for model, n in run_model.starmap([(m, samples, limit) for m in MODELS]):
        print(f"{model}: {n} attempts")
