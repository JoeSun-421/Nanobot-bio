# -*- coding: utf-8 -*-
"""Engineering maturity gates: pytest/ruff/layout + optional light eval."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], *, cwd: Optional[Path] = None) -> int:
    print("+", " ".join(cmd), flush=True)
    return int(subprocess.call(cmd, cwd=str(cwd or ROOT)))


def delivery_loo_ready() -> tuple[bool, str]:
    """Return (ok, reason) if light LOO CSVs are reachable."""
    try:
        from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths
        from rbp_eval.loo.loo_eval import resolve_loo_csvs

        apply_delivery_env()
        paths = resolve_delivery_paths()
        root = paths["delivery_root"]
        if not root.is_dir():
            return False, f"DELIVERY_ROOT missing: {root}"
        summary, metrics = resolve_loo_csvs()
        if not summary.is_file() or not metrics.is_file():
            return False, "LOO CSV missing (tried agent_db/transfer and agent/database/transfer)"
        return True, str(root)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def assert_loo_report(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("n") or 0) < 10:
        raise AssertionError(f"LOO report n<10: {data.get('n')} in {path}")
    if "summary" not in data or "rows" not in data:
        raise AssertionError(f"LOO report missing summary/rows: {path}")


def assert_eval_plan_report(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "held_out_split" not in data:
        raise AssertionError(f"eval-plan missing held_out_split: {path}")
    hos = data["held_out_split"]
    if int(hos.get("n_held") or 0) < 1 and not hos.get("held_out_rbps"):
        raise AssertionError(f"eval-plan held_out_split empty: {path}")
    pm = data.get("primary_metrics") or {}
    if "transfer_level" not in pm:
        raise AssertionError(f"eval-plan missing primary_metrics.transfer_level: {path}")


def run_gate(*, skip_eval: bool = False, with_cov: bool = True) -> int:
    """Run Phase-1 local/CI gate. Return process exit code."""
    from app.core.paths import ensure_artifact_dirs, report_path

    ensure_artifact_dirs()
    failures: list[str] = []

    if _run([sys.executable, "-m", "ruff", "check", "app", "rbp_eval", "tests"]):
        failures.append("ruff")

    pytest_cmd = [sys.executable, "-m", "pytest", "-q"]
    if not with_cov:
        pytest_cmd.append("--no-cov")
    if _run(pytest_cmd):
        failures.append("pytest")

    env = os.environ.copy()
    # SoT is the in-repo slim package (Proposal §6.2), matching app/agent.py and
    # `rbp-agent layout`; never the fat BIO_ROOT sibling clone.
    env.setdefault("NANOBOT_SRC", str(ROOT / "nanobot"))
    print("+ rbp-agent layout", flush=True)
    lay = subprocess.call(
        [sys.executable, "-m", "app", "layout"],
        cwd=str(ROOT),
        env=env,
    )
    if lay:
        failures.append("layout")

    ready, reason = delivery_loo_ready()
    eval_status: dict[str, Any] = {"ran": False, "skipped": True, "reason": reason}
    if skip_eval:
        print(f"[gate] skip eval (--skip-eval): {reason}")
    elif not ready:
        print(f"[gate] skip eval (no delivery LOO): {reason}")
    else:
        eval_status["skipped"] = False
        eval_status["ran"] = True
        loo_out = report_path("eval_loo_report.json")
        plan_out = report_path("evaluation_plan_report.json")
        if _run([sys.executable, "-m", "rbp_eval.loo.loo_eval", "--out", str(loo_out)]):
            failures.append("loo_eval")
        else:
            try:
                assert_loo_report(loo_out)
            except AssertionError as e:
                print(f"[gate] LOO assert failed: {e}", file=sys.stderr)
                failures.append("loo_assert")
        if _run([sys.executable, "-m", "app", "eval-plan", "--out", str(plan_out)]):
            failures.append("eval_plan")
        else:
            try:
                assert_eval_plan_report(plan_out)
            except AssertionError as e:
                print(f"[gate] eval-plan assert failed: {e}", file=sys.stderr)
                failures.append("eval_plan_assert")
        eval_status["loo_report"] = str(loo_out)
        eval_status["eval_plan_report"] = str(plan_out)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "ok": not failures,
        "eval": eval_status,
    }
    gate_path = report_path("gate_report.json")
    gate_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[gate] wrote {gate_path} ok={report['ok']} failures={failures}")
    return 0 if not failures else 1
