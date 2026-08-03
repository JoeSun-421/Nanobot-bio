# -*- coding: utf-8 -*-
"""User-facing commands: doctor, onboard, agent, chat, nanobot-smoke."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from app.cli.common import ROOT, read_fasta


def _ensure_llm_configured() -> int:
    """Ensure a usable LLM API key exists; auto-launch onboarding when missing.

    Returns 0 when a usable key is present (or was just created), else 1.
    Checks the active provider key (preferring ``nanobot-bio/.env``), not merely
    whether ``~/.nanobot/config.json`` exists — a config without a key used to
    hard-fail with ``No API key configured for provider '…'``.
    On a TTY we run the onboarding wizard inline then continue; non-interactive
    contexts keep a clear, scriptable error.
    """
    from app.core.onboard import (
        DEFAULT_CONFIG,
        interactive_onboard,
        llm_is_configured,
        prepare_llm_config,
    )

    cfg = Path(os.environ.get("NANOBOT_CONFIG", str(DEFAULT_CONFIG))).expanduser()
    prepare_llm_config(cfg, persist=True)
    if llm_is_configured(cfg):
        return 0

    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive:
        print(
            "No LLM provider/API key configured. Run:  rbp-agent onboard\n"
            "(pick a provider explicitly — there is no default — e.g.:\n"
            "  rbp-agent onboard --provider openai --model gpt-5.6 --key ...\n"
            "  rbp-agent onboard --provider deepseek --model deepseek-v4-pro --key ...\n"
            " or put the matching *_API_KEY=… in nanobot-bio/.env)",
            file=sys.stderr,
        )
        return 1
    print("No LLM provider/API key configured — let's set one up.\n")
    try:
        ok = interactive_onboard(cfg)
    except KeyboardInterrupt:
        print("\nOnboarding cancelled.", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"Onboarding failed: {e}", file=sys.stderr)
        print("Run:  rbp-agent onboard", file=sys.stderr)
        return 1
    prepare_llm_config(cfg, persist=True)
    if not ok or not llm_is_configured(cfg):
        print("Onboarding did not complete. Run:  rbp-agent onboard", file=sys.stderr)
        return 1
    print("\nLLM configured. Starting chat...\n")
    return 0


def _is_missing_api_key_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "no api key configured" in msg or (
        "api key" in msg and "not set" in msg
    )


def _start_nanobot_with_onboard(agent) -> int:
    """Call ``agent.get_nanobot()``; on missing-key errors, onboard then retry once."""
    try:
        agent.get_nanobot()
        return 0
    except Exception as e:
        if not _is_missing_api_key_error(e):
            print(f"Failed to start: {e}", file=sys.stderr)
            return 1
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if not interactive:
            print(f"Failed to start: {e}", file=sys.stderr)
            print("Fix: rbp-agent onboard   (set provider + API key)", file=sys.stderr)
            return 1
        print("LLM API key missing — opening configuration...\n", file=sys.stderr)
        if _ensure_llm_configured() != 0:
            return 1
        agent._bot = None  # force rebuild with fresh config / .env
        try:
            agent.get_nanobot()
            return 0
        except Exception as e2:
            print(f"Failed to start: {e2}", file=sys.stderr)
            return 1


def _cmd_agent_fasta(args: argparse.Namespace) -> int:
    """Batch own-head FASTA score (score_binding_fasta; no LLM)."""
    query = (getattr(args, "query", None) or "").strip()
    fasta = getattr(args, "fasta", None)
    if not query:
        print("ERROR: --fasta requires --query RBP alias", file=sys.stderr)
        return 2
    if not fasta:
        print("ERROR: --fasta path required", file=sys.stderr)
        return 2
    from nanobot.agent.tools.rbp.fasta_score import run_fasta_score

    try:
        from app.core.chat_ux import print_banner

        print_banner(subtitle="batch FASTA score · no LLM")
    except Exception:
        pass
    out = run_fasta_score(
        path=str(fasta),
        rbp=query,
        cohort="K562",
        batch_size=64,
        max_seqs=getattr(args, "max_seqs", None),
        device=getattr(args, "device", None) or "auto",
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {out_path}", file=sys.stderr)
    return 0 if out.get("ok") else 1


def _cmd_agent_doc(args: argparse.Namespace) -> int:
    """Print allowlisted markdown chunk (read_project_doc; no LLM)."""
    from nanobot.agent.tools.rbp.project_doc import read_project_doc

    out = read_project_doc(path=str(args.doc), offset=0, max_chars=24000)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


def _looks_like_suite_path_message(msg: str) -> bool:
    """True when chat should short-circuit to outer-loop prompt-suite batch."""
    try:
        from nanobot.agent.tools.rbp.prompt_suite import is_prompt_suite_request

        return bool(is_prompt_suite_request(msg))
    except Exception:
        return False


def _run_chat_prompt_suite(msg: str, *, device: str = "auto") -> None:
    """Read full user message, apply suite filters, run outer-loop batch.

    Never ignores non-path instructions (e.g. ``最后三条``). If the message
    has leftover intent we cannot parse confidently, ask for clarification
    instead of silently running the full suite.
    """
    from nanobot.agent.tools.rbp.prompt_suite import (
        extract_suite_path_candidate,
        parse_suite_message_options,
        run_prompt_suite,
    )

    opts = parse_suite_message_options(msg)
    path = extract_suite_path_candidate(msg)
    if not path:
        print(
            "  usage: /suite docs/eval/UNSEEN_RBP_TEST_PROMPTS_20.md "
            "[--dry-run] [--limit N] [--offset N] [--last N] [--case GENE]",
            file=sys.stderr,
        )
        print(
            "  or paste a suite path + filter, e.g.\n"
            "    docs/eval/transfer_test_prompts.md 读取最后三条\n"
            "    /suite docs/eval/transfer_test_prompts.md --last 3",
            file=sys.stderr,
        )
        return

    if opts.needs_clarification:
        print(f"  ▸ prompt suite · {path}", file=sys.stderr)
        print(
            "  ⚠ message has instructions beyond the suite path, but no clear "
            "case filter was parsed (last N / first N / --limit / --offset / "
            "--case / Prompt NN).\n"
            "  Not running the full suite. Re-send with an explicit filter, e.g.:\n"
            "    …/transfer_test_prompts.md 读取最后三条\n"
            "    /suite …/transfer_test_prompts.md --last 3\n"
            "    /suite …/transfer_test_prompts.md --limit 3\n"
            "    /suite …/transfer_test_prompts.md --case 18 --case 19 --case 20",
            file=sys.stderr,
        )
        return

    print(f"  ▸ prompt suite · {path}", file=sys.stderr)
    if opts.dry_run:
        print("  · dry-run (parse only)", file=sys.stderr)
    if opts.has_explicit_filter:
        bits = []
        if opts.last is not None:
            bits.append(f"last={opts.last}")
        if opts.limit is not None:
            bits.append(f"limit={opts.limit}")
        if opts.offset is not None:
            bits.append(f"offset={opts.offset}")
        if opts.cases:
            bits.append("case=" + ",".join(opts.cases))
        if bits:
            print(f"  · filter {' '.join(bits)}", file=sys.stderr)
    t0 = time.perf_counter()
    try:
        report = run_prompt_suite(
            path=path,
            cases=opts.cases,
            limit=opts.limit,
            offset=opts.offset,
            last=opts.last,
            device=device,
            dry_run=bool(opts.dry_run),
            stream=True,
        )
    except KeyboardInterrupt:
        print("\n  ⚠ suite interrupted", file=sys.stderr)
        return
    except Exception as e:
        print(f"  ✗ suite error: {type(e).__name__}: {e}", file=sys.stderr)
        return

    elapsed = time.perf_counter() - t0
    if report.get("error") and not report.get("n_cases"):
        print(f"  ✗ {report.get('error')}", file=sys.stderr)
        return

    sel = report.get("selection")
    print(
        f"  suite ok={report.get('ok')} "
        f"n_ok={report.get('n_ok')}/{report.get('n_cases')} "
        + (f"({sel}) " if sel else "")
        + f"elapsed={elapsed:.1f}s",
        file=sys.stderr,
    )
    if report.get("summary_json"):
        print(f"  summary  {report.get('summary_json')}", file=sys.stderr)
    if report.get("jsonl"):
        print(f"  jsonl    {report.get('jsonl')}", file=sys.stderr)
    for r in report.get("results") or []:
        if isinstance(r, str):
            print(f"  - {r}", file=sys.stderr)
            continue
        if report.get("dry_run"):
            print(f"  - {r.get('case')}", file=sys.stderr)
            continue
        status = "ok" if r.get("ok") else "FAIL"
        print(
            f"  [{status}] {r.get('case')} label={r.get('label')} "
            f"p_hat={r.get('p_hat')} mode={r.get('path_mode')}"
            + (f" err={r.get('error')}" if r.get("error") else ""),
            file=sys.stderr,
        )


def cmd_agent(args: argparse.Namespace) -> int:
    """One-shot Nanobot.run (primary agent path). No pipeline fallback."""
    from app.core.chat_ux import (
        configure_chat_logging,
        format_verdict_display,
        memory_blocker_message,
        print_banner,
        print_registration,
        print_verdict_block,
        run_agent_turn_streamed_sync,
    )
    from app.agent import skill_path as _skill_path

    configure_chat_logging(verbose=bool(getattr(args, "verbose", False)))

    # Short-circuit: batch FASTA score / doc read (no LLM).
    if getattr(args, "fasta", None):
        return _cmd_agent_fasta(args)
    if getattr(args, "doc", None):
        return _cmd_agent_doc(args)

    print_banner(subtitle="one-shot agent · thinking + tools visible")
    warn = memory_blocker_message()
    if warn:
        print(warn, file=sys.stderr)

    if _ensure_llm_configured() != 0:
        return 1

    try:
        from app.agent import RBPAgent
    except ImportError as e:
        print("integrate import failed:", e, file=sys.stderr)
        return 1

    try:
        from rbp_eval.runtime.nanobot_hooks import RBPTraceHook
    except ImportError:
        from rbp_eval.runtime.hooks import JsonlTraceHook as RBPTraceHook

    if getattr(args, "example", None):
        from app.backends.delivery.examples import own_head_prompt

        message = own_head_prompt(args.example)
    elif getattr(args, "message", None):
        message = args.message
    else:
        parts = []
        if args.query:
            parts.append(f"RBP {args.query}")
        if args.uniprot:
            parts.append(f"target_uniprot: {args.uniprot}")
        if args.rna_file:
            raw = Path(args.rna_file).read_text(encoding="utf-8")
            rna = "".join(
                ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith(">")
            )
            parts.append(f"RNA: {rna}")
        if args.sequence_fasta:
            seq = read_fasta(Path(args.sequence_fasta))
            parts.append(f"protein_sequence: {seq[:80]}... (len={len(seq)})")
            parts.append(f"FULL_SEQ: {seq}")
        if args.force_transfer:
            parts.append(
                "force_transfer: treat target as unseen even if in_panel "
                "(run Stage 1–3; do not use own-head stop)."
            )
        if not parts:
            print(
                "Need --message, --example pos|neg, --query/--rna-file, "
                "--query/--fasta, or --doc.\n"
                "Ideal-env own-head smoke:  rbp-agent agent --example pos\n"
                "Batch FASTA: nanobot-bio agent --query FXR2 --fasta path/to/test.fasta",
                file=sys.stderr,
            )
            return 2
        message = "Does this RNA interact with the target RBP? " + " ; ".join(parts)

    if getattr(args, "fallback", False) or getattr(args, "offline", False):
        print(
            "ERROR: pipeline fallback removed from product CLI.\n"
            "Use Nanobot agent path only (rbp-agent agent|chat|own-head).",
            file=sys.stderr,
        )
        return 2

    from app.core.paths import TRACES, ensure_artifact_dirs

    ensure_artifact_dirs()
    trace = TRACES / "cli_agent.jsonl"
    try:
        from nanobot.agent.tools.rbp.annotation import reset_tool_turn_guards

        reset_tool_turn_guards()
    except Exception:
        pass

    agent = RBPAgent(
        offline=False,
        device=args.device or "auto",
        use_conda=True,
        prefer_nanobot_llm=True,
        allow_fallback=False,
        auto_install_into_nanobot=False,
        hooks=[RBPTraceHook(trace)],
    )
    if _start_nanobot_with_onboard(agent) != 0:
        return 1
    print_registration(agent.tool_names, skill_path=_skill_path())

    prompt = (
        message
        + "\n\n[Output contract] Reply with ONE raw JSON object only "
        "(no markdown fences). Fields: label, p_hat, confidence, "
        "explanation, supporting_rbps. "
        "If resolve_rbp.in_panel=true: own-head predict once then STOP. "
        "`p_hat` comes only from predict tools."
    )
    result = run_agent_turn_streamed_sync(
        agent,
        prompt,
        session_key=getattr(args, "session_key", None) or "rbp:cli",
        extra_hooks=[],
    )
    display = format_verdict_display(result)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(display, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print_verdict_block(display)
    if getattr(args, "strict", False) and result.mode != "nanobot_llm":
        return 2
    return 0 if result.mode != "error" else 1


def cmd_chat(args: argparse.Namespace) -> int:
    """Multi-turn agent: quiet logs, visible thinking/tools, JSON verdict."""
    from app.core.chat_ux import (
        CHAT_HELP,
        configure_chat_logging,
        format_verdict_display,
        memory_blocker_message,
        print_chat_header,
        print_registration,
        print_status_panel,
        print_turn_footer,
        print_verdict_block,
        read_user_message,
        run_agent_turn_streamed_sync,
    )
    from app.agent import skill_path as _skill_path

    verbose = bool(getattr(args, "verbose", False))
    configure_chat_logging(verbose=verbose)

    try:
        from app.agent import RBPAgent
    except ImportError as e:
        print("Failed to import app.agent:", e, file=sys.stderr)
        return 1
    try:
        from rbp_eval.runtime.nanobot_hooks import RBPTraceHook
    except ImportError:
        from rbp_eval.runtime.hooks import JsonlTraceHook as RBPTraceHook

    if _ensure_llm_configured() != 0:
        return 1

    session_key = getattr(args, "session_key", None) or f"chat-{os.getpid()}"
    device = getattr(args, "device", None) or "auto"
    from app.core.paths import TRACES, ensure_artifact_dirs

    ensure_artifact_dirs()
    trace = TRACES / "cli_chat.jsonl"

    agent = RBPAgent(
        offline=False,
        device=device,
        use_conda=True,
        prefer_nanobot_llm=True,
        allow_fallback=False,
        auto_install_into_nanobot=False,
        hooks=[RBPTraceHook(trace)],
    )
    if _start_nanobot_with_onboard(agent) != 0:
        return 1

    try:
        from app.core.onboard import current_summary

        summary = current_summary()
    except Exception:
        summary = "?"

    skill = _skill_path()
    skill_ok = bool(skill and skill.is_file())
    print_chat_header(
        llm_summary=summary,
        n_tools=len(agent.tool_names),
        skill_ok=skill_ok,
        mem_warn=memory_blocker_message(),
        session_key=session_key,
    )
    print_registration(agent.tool_names, skill_path=skill)

    while True:
        msg = read_user_message("❯ ")
        if msg is None:
            print()
            return 0
        msg = msg.strip()
        if not msg:
            continue
        low = msg.lower().split()[0] if msg else ""

        if low in ("/quit", "/exit", "quit", "exit"):
            print("bye.", file=sys.stderr)
            return 0
        if low in ("/help", "/?"):
            print(CHAT_HELP, file=sys.stderr)
            continue
        if low == "/status":
            print_status_panel(
                llm_summary=summary,
                n_tools=len(agent.tool_names),
                session_key=session_key,
                skill_ok=skill_ok,
            )
            continue
        if low == "/tools":
            names = sorted(agent.tool_names)
            print(f"  {len(names)} tools:", file=sys.stderr)
            for i in range(0, len(names), 4):
                print("   ", "  ".join(names[i : i + 4]), file=sys.stderr)
            print(file=sys.stderr)
            continue
        if low in ("/new", "/reset"):
            session_key = f"chat-{os.getpid()}-{int(__import__('time').time())}"
            print(f"  ✓ new session · {session_key}", file=sys.stderr)
            continue
        if low == "/clear":
            sys.stderr.write("\033[2J\033[H")
            sys.stderr.flush()
            print_chat_header(
                llm_summary=summary,
                n_tools=len(agent.tool_names),
                skill_ok=skill_ok,
                session_key=session_key,
            )
            continue
        if low == "/thinking":
            cur = os.environ.get("RBP_SHOW_THINKING", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "full",
                "expand",
            )
            if cur:
                os.environ.pop("RBP_SHOW_THINKING", None)
                print("  thinking folded (default)", file=sys.stderr)
            else:
                os.environ["RBP_SHOW_THINKING"] = "1"
                print("  thinking expanded", file=sys.stderr)
            continue
        if low == "/caveats":
            cur = os.environ.get("RBP_SHOW_CAVEATS", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "full",
                "expand",
            )
            if cur:
                os.environ.pop("RBP_SHOW_CAVEATS", None)
                print("  caveats folded (default)", file=sys.stderr)
            else:
                os.environ["RBP_SHOW_CAVEATS"] = "1"
                print("  caveats expanded", file=sys.stderr)
            continue
        if low == "/suite" or _looks_like_suite_path_message(msg):
            _run_chat_prompt_suite(msg, device=device)
            continue
        if low in ("/onboard", "/login"):
            from app.core.onboard import current_summary, interactive_onboard, prepare_llm_config

            if interactive_onboard():
                prepare_llm_config(persist=True)
                agent._bot = None
                if _start_nanobot_with_onboard(agent) != 0:
                    print("  ⚠ LLM still not ready after onboard", file=sys.stderr)
                try:
                    summary = current_summary()
                except Exception:
                    pass
            continue

        try:
            from nanobot.agent.tools.rbp.annotation import reset_tool_turn_guards

            reset_tool_turn_guards()
        except Exception:
            pass

        prompt = (
            msg
            + "\n\n[Output contract] Reply with ONE raw JSON object only "
            "(no markdown fences, no nested JSON). Fields: label, p_hat, "
            "confidence, explanation (plain sentences), supporting_rbps. "
            "If resolve_rbp.in_panel=true: own-head predict once then STOP. "
            "`p_hat` comes only from predict tools."
        )
        t0 = __import__("time").perf_counter()
        try:
            result = run_agent_turn_streamed_sync(
                agent, prompt, session_key=session_key, extra_hooks=[]
            )
        except KeyboardInterrupt:
            print("\n  ⚠ interrupted — ready for next message", file=sys.stderr)
            continue
        except Exception as e:
            print(f"  ✗ error: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        print_verdict_block(format_verdict_display(result))
        elapsed = float(getattr(result, "_ux_elapsed", None) or (time.perf_counter() - t0))
        n_tools = len(getattr(result, "_ux_tools", None) or [])
        print_turn_footer(
            elapsed_s=elapsed,
            mode=getattr(result, "mode", "") or "",
            n_tools=n_tools,
        )


def _doctor_print_table(rows: list[tuple[str, str, str]]) -> None:
    """Print Feature / Status / Detail table; anomalies first."""
    order = {"FAIL": 0, "WARN": 1, "SKIP": 2, "OK": 3, "INFO": 4}
    ranked = sorted(rows, key=lambda r: (order.get(r[1], 9), r[0]))
    w_f = max(len("Feature"), max((len(r[0]) for r in ranked), default=7))
    w_s = max(len("Status"), max((len(r[1]) for r in ranked), default=6))
    print(f"{'Feature':<{w_f}}  {'Status':<{w_s}}  Detail")
    print(f"{'-' * w_f}  {'-' * w_s}  {'-' * 6}")
    for feat, st, detail in ranked:
        d = (detail or "").replace("\n", " ")
        if len(d) > 96:
            d = d[:93] + "..."
        print(f"{feat:<{w_f}}  {st:<{w_s}}  {d}")


def cmd_doctor(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from app.backends.delivery.client import DeliveryToolClient, SCRIPT_MAP, tools_meta_by_name
    from app.backends.delivery.env import apply_delivery_env, conda_env_python, resolve_delivery_paths
    from app.core.chat_ux import cgroup_memory_gb, memory_blocker_message
    from app.core.paths import ARTIFACTS, describe_canonical_stores, ensure_artifact_dirs

    verbose = bool(getattr(args, "verbose", False))
    apply_delivery_env()
    sync_ok = False
    sync_err = None
    try:
        from app.sync_overlay import sync_overlay

        sync_ok = sync_overlay(quiet=True) == 0
    except Exception as e:
        sync_err = f"{type(e).__name__}: {e}"
    dirs = ensure_artifact_dirs()
    stores = describe_canonical_stores()
    paths = resolve_delivery_paths()
    path_status: dict[str, dict[str, object]] = {}
    for k in ("rbp_registry", "predict_api", "registry_json", "agent_db", "rhobind_release"):
        p = paths[k]
        path_status[k] = {"ok": p.exists(), "path": str(p)}

    meta = tools_meta_by_name()
    missing = [n for n in SCRIPT_MAP if not (paths["delivery_root"] / SCRIPT_MAP[n]).is_file()]
    gb = cgroup_memory_gb()
    mem_warn = memory_blocker_message()

    rhobind_py = None
    protein_embed_py = None
    rna_py = None
    rhobind_pkgs_ok = False
    rhobind_pkgs_detail = ""
    rhobind_cuda = False
    try:
        from app.backends.delivery.client import DeliveryToolClient as _DTC

        for env_name, slot in (
            ("rhobind", "rhobind"),
            ("protein_embed", "embed"),
            ("rna", "rna"),
        ):
            pref = _DTC._conda_env_prefix(env_name)
            if pref is not None:
                cand = pref / "bin" / "python"
                if cand.is_file():
                    if slot == "rhobind":
                        rhobind_py = cand
                    elif slot == "embed":
                        protein_embed_py = cand
                    else:
                        rna_py = cand
    except Exception:
        pass
    if rhobind_py is not None:
        try:
            import subprocess as _sp_rh

            probe = _sp_rh.run(
                [
                    str(rhobind_py),
                    "-c",
                    "import torch, transformers; "
                    "print(torch.__version__, transformers.__version__, int(torch.cuda.is_available()))",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if probe.returncode == 0:
                rhobind_pkgs_ok = True
                parts = (probe.stdout or "").strip().split()
                rhobind_pkgs_detail = " ".join(parts[:2]) if parts else (probe.stdout or "").strip()
                if len(parts) >= 3 and parts[2] == "1":
                    rhobind_cuda = True
                    rhobind_pkgs_detail += " cuda=yes"
                else:
                    rhobind_pkgs_detail += " cuda=no"
            else:
                rhobind_pkgs_detail = (
                    (probe.stderr or probe.stdout or "import failed").strip()[:200]
                )
        except Exception as e:
            rhobind_pkgs_detail = f"{type(e).__name__}: {e}"[:200]
    else:
        rhobind_pkgs_detail = "no rhobind python — run: scripts/nbio setup"

    mmseqs_ok = False
    mmseqs_detail = ""
    if rna_py is not None:
        # Direct env python does not put env bin on PATH (same caveat as
        # DeliveryToolClient). Prefer the sibling binary next to rna python —
        # that is how tools set MMSEQS / prepend PATH for rna_blastn etc.
        sibling_mm = rna_py.parent / "mmseqs"
        if sibling_mm.is_file():
            mmseqs_ok = True
            mmseqs_detail = str(sibling_mm)
        else:
            try:
                import os as _os_mm
                import subprocess as _sp_mm

                env_mm = _os_mm.environ.copy()
                env_mm["PATH"] = f"{rna_py.parent}:{env_mm.get('PATH', '')}"
                mm = _sp_mm.run(
                    [
                        str(rna_py),
                        "-c",
                        "import shutil; print(shutil.which('mmseqs') or '')",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=env_mm,
                )
                path_mm = (mm.stdout or "").strip()
                if mm.returncode == 0 and path_mm:
                    mmseqs_ok = True
                    mmseqs_detail = path_mm
                else:
                    mmseqs_detail = "mmseqs not installed in rna env bin"
            except Exception as e:
                mmseqs_detail = f"{type(e).__name__}: {e}"[:160]
    else:
        mmseqs_detail = "no rna conda env"

    cli = DeliveryToolClient(offline=True, device="cpu", use_conda=False)
    r = cli.call("resolve_rbp", {"query": "PTBP1"})
    golden_ok = False
    golden_detail = ""
    try:
        from app.backends.delivery.examples import load_example

        ex = load_example("pos")
        golden_ok = True
        golden_detail = f"rna_len={len(ex['rna'])} path={ex['rna_path']}"
    except Exception as e:
        golden_detail = str(e)

    skill = ROOT / "nanobot" / "skills" / "rbp-agent" / "SKILL.md"
    skill_ok = skill.is_file() and "always: true" in skill.read_text(encoding="utf-8")

    axes_detail = ""
    axes_ok = True
    try:
        from app.backends.delivery.stage_tools import (
            assert_full_axes_enabled,
            axis_status_matrix,
        )
        from app.core.runtime_config import load_runtime_config

        _cfg = load_runtime_config()
        _axes = _cfg.get("axes") or {}
        _off = assert_full_axes_enabled(_axes)
        _st = axis_status_matrix(_axes)
        if _off:
            axes_ok = False
            axes_detail = f"REQUIRED_OFF={','.join(_off)}"
        else:
            axes_detail = f"use_af3={_axes.get('use_af3')} af3={_st.get('use_af3', 'n/a')}"
    except Exception as e:
        axes_ok = False
        axes_detail = f"{type(e).__name__}: {e}"

    matrix_path = None
    delivery_smoke_status: dict[str, object] = {}
    rna_feature_status: dict[str, object] = {}
    af3_feature_status: dict[str, object] = {}
    try:
        from app.core.capability_matrix import probe_capabilities, write_capability_matrix

        matrix_path = write_capability_matrix()
        caps = probe_capabilities()
        feats = caps.get("features") or {}
        delivery_smoke_status = dict(feats.get("delivery_tool_smoke") or {})
        rna_feature_status = dict(feats.get("rna_blastn") or {})
        af3_feature_status = dict(feats.get("af3") or {})
    except Exception as e:
        delivery_smoke_status = {"status": "error", "detail": f"{type(e).__name__}: {e}"}

    esm_ok = False
    esm_detail = ""
    try:
        from nanobot.agent.tools.rbp.common import load_catalogue_sequence

        seq = load_catalogue_sequence("PTBP1") or ""
        esm_cli = DeliveryToolClient(offline=True, device="cpu", use_conda=True)
        if not seq:
            esm_detail = "no catalogue sequence for PTBP1"
        else:
            esm = esm_cli.call(
                "esm_similarity",
                {
                    "sequence": seq,
                    "encoder": "esmc",
                    "device": "cpu",
                    "top_k": 3,
                },
            )
            hits = esm.get("hits") or []
            err_s = str(esm.get("error") or "")
            if hits and not esm.get("error"):
                esm_ok = True
                top = hits[0]
                esm_detail = (
                    f"top={top.get('alias')} score={top.get('score')} "
                    f"n_hits={len(hits)}"
                )
            elif "rc=-9" in err_s or "Killed" in err_s:
                esm_detail = (
                    "killed/OOM (rc=-9) — raise cgroup memory for protein_embed; "
                    + err_s[:160]
                )
            else:
                esm_detail = (err_s or "no hits")[:240]
    except Exception as e:
        esm_detail = f"{type(e).__name__}: {e}"[:240]

    af3_ok = False
    af3_detail = ""
    try:
        import subprocess as _sp

        af3_py = os.environ.get("AF3_PYTHON") or ""
        if not af3_py or af3_py == "/bin/false" or not Path(af3_py).is_file():
            # Portable rediscovery if activate skipped AF3
            for name in ("af3_blackwell", "af3"):
                cand = conda_env_python(name)
                if cand is not None and cand.is_file():
                    af3_py = str(cand)
                    break
        if not af3_py or af3_py == "/bin/false" or not Path(af3_py).is_file():
            af3_detail = "AF3_PYTHON unset (optional; set AF3_PYTHON or install af3 conda env)"
        elif "/.venv/" in af3_py:
            af3_detail = f"AF3_PYTHON points at agent venv (wrong): {af3_py}"
        else:
            probe = _sp.run(
                [af3_py, "-c", "import alphafold3; print(alphafold3.__file__)"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if probe.returncode == 0:
                af3_ok = True
                af3_detail = f"python={af3_py}"
            else:
                af3_detail = (
                    f"python={af3_py} cannot import alphafold3: "
                    + (probe.stderr or probe.stdout or "").strip()[:200]
                )
    except Exception as e:
        af3_detail = f"{type(e).__name__}: {e}"[:240]

    try:
        from app.core.onboard import llm_is_configured

        llm_key_ok = llm_is_configured()
    except Exception:
        llm_key_ok = bool(
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )

    delivery_root = Path(paths["delivery_root"])
    delivery_ok = delivery_root.is_dir() and bool(path_status["rbp_registry"]["ok"])
    venv_py = sys.executable
    peaks_ok = rna_feature_status.get("status") == "ready"
    af3_feat = str(af3_feature_status.get("status") or "unknown")
    if af3_ok and af3_feat == "ready":
        af3_status, af3_row = "OK", af3_detail
    elif af3_ok:
        af3_status, af3_row = "WARN", f"{af3_detail} feature={af3_feat}"
    elif af3_feat in {"off", "disabled", "skipped"}:
        af3_status, af3_row = "SKIP", af3_detail or f"feature={af3_feat}"
    else:
        af3_status, af3_row = "WARN", af3_detail or "optional structure fallback"

    rows: list[tuple[str, str, str]] = [
        ("Agent venv / CLI", "OK" if Path(venv_py).is_file() else "FAIL", venv_py),
        (
            "Delivery pack",
            "OK" if delivery_ok else "FAIL",
            str(delivery_root) if delivery_ok else "set DELIVERY_ROOT / sibling pack",
        ),
        (
            "Own-head predict (rhobind)",
            "OK" if rhobind_pkgs_ok else "FAIL",
            rhobind_pkgs_detail
            + ("" if rhobind_pkgs_ok or rhobind_cuda else "; fix: scripts/nbio setup"),
        ),
        (
            "Transfer ESM (protein_embed)",
            "OK" if esm_ok else ("WARN" if protein_embed_py else "FAIL"),
            esm_detail
            or (
                str(protein_embed_py)
                if protein_embed_py
                else "missing protein_embed env — scripts/nbio setup"
            ),
        ),
        (
            "RNA tools (mmseqs)",
            "OK" if mmseqs_ok else "WARN",
            mmseqs_detail,
        ),
        (
            "PEAKS DB / rna_blastn",
            "OK" if peaks_ok else "WARN",
            str(rna_feature_status.get("status") or "not ready"),
        ),
        ("AF3 structure", af3_status, af3_row),
        (
            "LLM key",
            "OK" if llm_key_ok else "WARN",
            "configured" if llm_key_ok else "run: nanobot-bio onboard",
        ),
        (
            "Registry / resolve PTBP1",
            "OK" if r.get("matched") and r.get("in_panel") else "FAIL",
            f"matched={r.get('matched')} in_panel={r.get('in_panel')} head={r.get('head_index')}",
        ),
        (
            "Skill always-on",
            "OK" if skill_ok else "FAIL",
            str(skill),
        ),
        (
            "Required axes",
            "OK" if axes_ok else "FAIL",
            axes_detail,
        ),
        (
            "Golden example (pos)",
            "OK" if golden_ok else "WARN",
            golden_detail,
        ),
        (
            "SCRIPT_MAP tools",
            "OK" if not missing else "WARN",
            f"{len(SCRIPT_MAP) - len(missing)}/{len(SCRIPT_MAP)} present"
            + (f"; missing={missing[:5]}" if missing else ""),
        ),
        (
            "cgroup memory",
            "WARN" if mem_warn else "OK",
            ("unlimited" if gb is None else f"{gb:.2f} GiB")
            + ("; RhoBind may OOM" if mem_warn else ""),
        ),
    ]

    print("=== nanobot-bio doctor ===")
    print(f"DELIVERY_ROOT={paths['delivery_root']}")
    _doctor_print_table(rows)

    fix_hints: list[str] = []
    if not rhobind_pkgs_ok:
        fix_hints.append("Own-head FAIL → scripts/nbio setup  (hollow rhobind / missing torch)")
    if not esm_ok:
        fix_hints.append(
            "Transfer ESM weak → HF_HOME + protein_embed env; ≥8 GiB RAM; scripts/nbio setup"
        )
    if not delivery_ok:
        fix_hints.append("Delivery FAIL → place rhobind_agent_delivery sibling or export DELIVERY_ROOT")
    if not llm_key_ok:
        fix_hints.append("LLM WARN → nanobot-bio onboard")
    if af3_status == "WARN" and not af3_ok:
        fix_hints.append(
            "AF3 optional → export AF3_PYTHON=…/envs/af3/bin/python or scripts/nbio setup"
        )
    if fix_hints:
        print("\nFix hints:")
        for h in fix_hints:
            print(f"  • {h}")

    if verbose:
        print("\n--- verbose ---")
        for k, st in path_status.items():
            print(f"  {k}: {'OK' if st['ok'] else 'MISSING'}  {st['path']}")
        print(f"artifacts root: {ARTIFACTS}")
        for name, p in dirs.items():
            if name == "proxy_cache":
                print(f"  {name}: {'OK' if p.is_file() else 'absent'}  {p}")
            else:
                print(f"  {name}: {'OK' if p.exists() else 'MISSING'}  {p}")
        print(f"registry tools: {len(meta)}")
        print(f"HF_HOME={os.environ.get('HF_HOME') or '(unset)'}")
        print(f"HF_ENDPOINT={os.environ.get('HF_ENDPOINT') or '(unset)'}")
        print(f"capability matrix: {matrix_path or '(none)'}")
        print(f"sync_overlay: {'OK' if sync_ok else 'WARN'} {sync_err or ''}")

    envs_ok = bool(rhobind_py and rhobind_pkgs_ok and protein_embed_py and esm_ok)
    af3_real_ok = bool(af3_ok and af3_feature_status.get("status") == "ready")
    lights = {
        "science_envs": "GREEN" if envs_ok else "RED",
        "PEAKS_DB": "GREEN" if peaks_ok else "YELLOW",
        "AF3_real_smoke": "GREEN" if af3_real_ok else "RED",
        "LLM_key": "GREEN" if llm_key_ok else "YELLOW",
    }

    ok_bridge = bool(r.get("matched") and r.get("in_panel") and skill_ok)
    status = "FAIL"
    rc = 1
    warn_bits: list[str] = []
    if mem_warn:
        warn_bits.append("RhoBind may OOM")
    if not esm_ok:
        warn_bits.append("ESM not usable — transfer quality will drop")
    if not rhobind_pkgs_ok:
        warn_bits.append(
            "rhobind missing torch/transformers — own-head predict will fail; "
            "run: scripts/nbio setup"
        )
    if ok_bridge and warn_bits:
        status = "WARN"
        rc = 0
        print("\ndoctor: WARN (Stage-0 wiring OK; " + "; ".join(warn_bits) + ")")
    elif ok_bridge:
        status = "OK"
        rc = 0
        print("\ndoctor: OK")
    else:
        print("\ndoctor: FAIL")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "sync_overlay_ok": sync_ok,
        "sync_overlay_error": sync_err,
        "delivery_root": str(paths["delivery_root"]),
        "paths": path_status,
        "canonical_stores": stores,
        "script_map": {"total": len(SCRIPT_MAP), "missing": len(missing), "missing_names": missing[:20]},
        "registry_tools": len(meta),
        "cgroup_memory_gib": gb,
        "memory_warn": bool(mem_warn),
        "rhobind_python": str(rhobind_py) if rhobind_py else None,
        "rhobind_torch_transformers": {
            "ok": rhobind_pkgs_ok,
            "detail": rhobind_pkgs_detail,
            "cuda": rhobind_cuda,
        },
        "protein_embed_python": str(protein_embed_py) if protein_embed_py else None,
        "resolve_rbp": {
            "matched": r.get("matched"),
            "alias": r.get("alias"),
            "in_panel": r.get("in_panel"),
            "head_index": r.get("head_index"),
        },
        "golden_example_pos": {"ok": golden_ok, "detail": golden_detail},
        "skill_always_on": skill_ok,
        "esm_probe": {"ok": esm_ok, "detail": esm_detail},
        "hf_home": os.environ.get("HF_HOME"),
        "hf_endpoint": os.environ.get("HF_ENDPOINT"),
        "delivery_tool_smoke": delivery_smoke_status,
        "traffic_lights": lights,
        "capability_rows": [
            {"feature": f, "status": s, "detail": d} for f, s, d in rows
        ],
    }
    try:
        from app.backends.delivery.stage_tools import (
            assert_full_axes_enabled,
            axis_status_matrix,
        )
        from app.core.runtime_config import load_runtime_config

        _cfg = load_runtime_config()
        _axes = dict(_cfg.get("axes") or {})
        report["axes"] = {
            "required_off": assert_full_axes_enabled(_axes),
            "use_af3": bool(_axes.get("use_af3")),
            "status": axis_status_matrix(_axes),
            "prefer_afdb": (_cfg.get("structure_policy") or {}).get("prefer_afdb"),
        }
    except Exception as e:
        report["axes"] = {"error": f"{type(e).__name__}: {e}"}
    from app.core.paths import report_path as _report_path

    out = _report_path("doctor_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"doctor report: {out}")
    return rc


def cmd_nanobot_smoke(args: argparse.Namespace) -> int:
    from app.agent import RBPAgent

    agent = RBPAgent(allow_fallback=False, prefer_nanobot_llm=True)
    try:
        bot = agent.get_nanobot()
    except Exception as e:
        print(f"nanobot start failed: {e}")
        return 1
    print(f"tools={agent.tool_names}")
    print(f"bot={type(bot).__name__}")
    return 0 if agent.tool_names else 1


def cmd_onboard(args: argparse.Namespace) -> int:
    """Configure LLM provider + API key + model (``.env`` + nanobot config)."""
    from app.core.onboard import (
        current_summary,
        dotenv_path,
        env_key_for,
        interactive_onboard,
        list_models_text,
        prepare_llm_config,
        save_provider,
        DEFAULT_CONFIG,
    )

    if getattr(args, "list_models", False):
        print(list_models_text())
        return 0

    if getattr(args, "show", False):
        prepare_llm_config(persist=False)
        print(current_summary())
        return 0

    provider = getattr(args, "provider", None)
    if provider:
        model = getattr(args, "model", None)
        if not model:
            print("--model is required with --provider", file=sys.stderr)
            print("Tip: rbp-agent onboard --list-models", file=sys.stderr)
            return 2
        save_provider(
            provider=provider,
            model=model,
            api_key=getattr(args, "key", None),
            api_base=getattr(args, "api_base", None),
        )
        print(f"saved → {DEFAULT_CONFIG}  [{provider} · {model}]")
        if getattr(args, "key", None):
            print(f"API key → {dotenv_path()} ({env_key_for(provider)})")
        return 0

    return 0 if interactive_onboard() else 1

