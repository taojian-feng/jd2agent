"""Local job runner: lets a remote assistant queue allow-listed jobs without terminal access.

Start once, in a terminal that has your model credentials (e.g. ANTHROPIC_API_KEY, AI_ARCHITECT_MODEL):

    uv run python -m ai_architect.runner

It watches jobs/inbox/ for *.json files like {"job": "loop", "args": {"scenario": "...", "cloud": "aws"}},
runs each one, and writes jobs/out/<id>.log and jobs/out/<id>.status.json. Only the jobs in JOBS run,
with validated arguments: no arbitrary commands. Stop with Ctrl+C.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX, OUT, DONE = ROOT / "jobs" / "inbox", ROOT / "jobs" / "out", ROOT / "jobs" / "done"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
CLOUDS = {"aws", "azure", "gcp"}
TIMEOUT_S = 30 * 60


def _scenario(args: dict) -> str:
    s = str(args.get("scenario", "dealer-fault-diagnosis"))
    if not SLUG.match(s) or not (ROOT / "resources" / "scenarios" / f"{s}.md").exists():
        raise ValueError(f"unknown scenario {s!r}")
    return s


def _cloud(args: dict) -> str:
    c = str(args.get("cloud", "aws"))
    if c not in CLOUDS:
        raise ValueError(f"cloud must be one of {sorted(CLOUDS)}")
    return c


def build_command(job: str, args: dict) -> list[str]:
    py = [sys.executable]
    if job == "tests":
        cmd = py + ["-m", "unittest", "discover", "-s", "tests", "-t", "."]
        if args.get("pattern"):
            p = str(args["pattern"])
            if not re.match(r"^[A-Za-z0-9_.]+$", p):
                raise ValueError("bad test pattern")
            cmd += ["-k", p]
        return cmd
    if job == "design":
        return py + ["-m", "ai_architect.cli", "design", "--scenario", _scenario(args), "--cloud", _cloud(args)]
    if job == "loop":
        rounds = int(args.get("max_rounds", 2))
        if not 0 <= rounds <= 3:
            raise ValueError("max_rounds must be 0..3")
        return py + ["-m", "ai_architect.cli", "loop", "--scenario", _scenario(args), "--cloud", _cloud(args),
                     "--max-rounds", str(rounds)]
    if job == "review":
        run_id = str(args.get("run_id", ""))
        if not re.match(r"^[0-9]{8}-[0-9]{6}-[a-z0-9-]+$", run_id):
            raise ValueError("bad run_id")
        return py + ["-m", "ai_architect.cli", "review", "--run-id", run_id]
    if job == "probe":
        return py + ["-m", "ai_architect.cli", "probe"]
    if job == "sync":  # re-install dependencies after pyproject changes
        return ["uv", "sync", "--extra", "anthropic", "--extra", "dev"]
    raise ValueError(f"unknown job {job!r}; allowed: tests, design, loop, review, probe, sync")


def run_one(path: Path) -> None:
    job_id = path.stem
    status = {"id": job_id, "started": datetime.now().isoformat(timespec="seconds")}
    log = OUT / f"{job_id}.log"
    try:
        spec = json.loads(path.read_text())
        cmd = build_command(spec.get("job", ""), spec.get("args") or {})
        status["command"] = " ".join(cmd[1:] if cmd[0] == sys.executable else cmd)
        print(f"[{status['started']}] {job_id}: {status['command']}", flush=True)
        with log.open("w") as fh:
            proc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, timeout=TIMEOUT_S)
        status["exit_code"] = proc.returncode
        tail = log.read_text(errors="ignore").splitlines()
        result = next((l[7:] for l in reversed(tail) if l.startswith("RESULT ")), None)
        if result:
            status["result"] = json.loads(result)
    except subprocess.TimeoutExpired:
        status["exit_code"], status["error"] = -1, f"timed out after {TIMEOUT_S}s"
    except Exception as e:  # bad job file: report, don't crash the runner
        status["exit_code"], status["error"] = -2, str(e)
    status["finished"] = datetime.now().isoformat(timespec="seconds")
    (OUT / f"{job_id}.status.json").write_text(json.dumps(status, indent=1))
    path.rename(DONE / path.name)
    print(f"[{status['finished']}] {job_id}: exit {status['exit_code']}", flush=True)


def main() -> None:
    for d in (INBOX, OUT, DONE):
        d.mkdir(parents=True, exist_ok=True)
    print(f"ai-architect runner watching {INBOX} (Ctrl+C to stop)", flush=True)
    while True:
        for path in sorted(INBOX.glob("*.json")):
            run_one(path)
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("runner stopped")
