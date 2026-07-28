# -*- coding: utf-8 -*-
"""
DeliveryToolClient — sole App entrypoint for calling ``rhobind_agent_delivery``.

Contract reference: ``delivery/agent/AGENT_BUILD_SPEC.md``.

Call conventions
----------------
Each delivery tool exposes two equivalent entrypoints:

* CLI: ``python <script> --json '<payload-json>'`` → JSON on stdout
* In-process: ``from <module> import run; run(payload_dict)`` → ``dict``

Identifiers use ``{alias, uniprot}``; cohort queues are ``K562`` | ``HepG2``.
Shared types (``RbpHit``, ``Prediction``) are passed through unchanged.
Capability metadata (``network`` / ``gpu`` / ``status``) comes from
``tools/registry.json``.

Paths are resolved via environment variables set by
``env.apply_delivery_env`` / delivery ``setup.sh``
(``AGENT_DB``, ``RBP_REGISTRY``, ``EMB_BANK``, ``FOLDSEEK_DB``, ``SEQ_DB``,
``PEAKS_DB``, ``AFDB_DIR``, ``TRANSFER_DIR``, ``USALIGN``, ``RHOBIND_RELEASE``,
``AF3_DIR``, ``AF3_PARAMS``, …).

Heavy tools run in named conda envs (``protein_embed``, ``rna``, ``rhobind``,
``af3``); lighter tools import under any numpy-capable interpreter.

This module maps registry names to delivery scripts, invokes ``run(payload)``
via importlib for pure-Python tools, and uses subprocess for heavy tools.
If a conda env is missing, the call falls back to the current interpreter and
returns a structured error on failure (no synthetic science scores).

Out of scope: reimplementing ESM / RhoBind / Foldseek inside the App,
editing delivery sources, or fabricating binding scores when models are
unavailable (return ``ok=false`` + ``error`` instead).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .env import apply_delivery_env, delivery_root, resolve_delivery_paths
from .tool_mapping import delivery_script_map, validate_delivery_registry

# ---------------------------------------------------------------------------
# Tools that can import run() under any numpy-capable Python (no special
# conda env). Matches AGENT_BUILD_SPEC “any python3 (+numpy)”.
# ---------------------------------------------------------------------------
PURE_PYTHON_TOOLS = {
    "resolve_rbp",
    "structure_fetch",
    "pymol_util",
    "go_pfam_lookup",
    "function_category",
    "uniprot_annotation",
    "pdb_metadata",
    "literature_retrieval",
    "domain_architecture",
    "rna_preprocess",
    "similarity_weighted_vote",
    "transfer_prior_lookup",
    "confidence_abstain",
    "donor_quality_prior",
    "colabfold_msa",  # urllib only; no AF3
}

# Heavy tools → conda environment name
DEFAULT_CONDA_ENV: dict[str, str] = {
    "struct_similarity_foldseek": "protein_embed",
    "struct_align_usalign": "protein_embed",
    "structure_consensus": "protein_embed",
    "esm_embed": "protein_embed",
    "esm_similarity": "protein_embed",
    "protein_seq_similarity": "rna",
    "rna_blastn": "rna",
    "structure_predict_af3": "af3",
    "rhobind_predict": "rhobind",
}

# Delivery scripts call ``$MMSEQS search`` without ``--threads``. Default
# all-core search can segfault (mmseqs: "World Size: … dbSize: …").
_MMSEQS_THREAD_TOOLS = frozenset({"rna_blastn", "protein_seq_similarity"})
_MMSEQS_WRAP = Path(__file__).resolve().parent / "mmseqs_wrap.sh"

# Registry tool name → script path relative to DELIVERY_ROOT.  This compatibility
# export is generated from mapping.yaml; it is no longer an independently edited
# whitelist.
SCRIPT_MAP: dict[str, str] = delivery_script_map()


def _adapt_colabfold_msa(mod: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Adapter: colabfold_msa exposes get_msa(), not run(payload)."""
    seq = payload.get("sequence") or payload.get("seq") or ""
    if not seq:
        return {"ok": False, "error": "colabfold_msa needs 'sequence'"}
    r = mod.get_msa(seq, mode=payload.get("mode", "env"))
    return {
        "ok": True,
        "n_seqs": r.get("n_seqs"),
        "ticket": r.get("ticket"),
        "preview": (r.get("a3m") or "")[:120],
    }


# Delivery tools without a run(payload) entrypoint — bridged via a thin adapter.
_IMPORT_ADAPTERS: dict[str, Any] = {
    "colabfold_msa": _adapt_colabfold_msa,
}


def load_delivery_registry() -> dict[str, Any]:
    """Load delivery ``tools/registry.json`` (authoritative tool list)."""
    apply_delivery_env()
    p = resolve_delivery_paths()["registry_json"]
    with open(p, encoding="utf-8") as f:
        registry = json.load(f)
    validate_delivery_registry(registry, delivery_root=delivery_root())
    return registry


def tools_meta_by_name() -> dict[str, dict[str, Any]]:
    reg = load_delivery_registry()
    return {t["name"]: t for t in reg.get("tools", []) if "name" in t}


class DeliveryToolClient:
    """
    Invoke a delivery script by registry tool name.

    Example (in-process entry equivalent to BUILD_SPEC)::

        apply_delivery_env()  # or: source agent/setup.sh
        cli = DeliveryToolClient(device="cpu")
        out = cli.call("resolve_rbp", {"query": "PTBP1"})
        # ``out`` is the dict returned by delivery ``resolve_rbp.run()``

    Failures return an error envelope instead of raising::

        {"ok": False, "tool": name, "error": "...", "_latency_ms": ...}
    """

    def __init__(
        self,
        *,
        offline: bool = False,
        prefer_import: bool = True,
        device: str = "cpu",
        use_conda: bool = True,
        conda_envs: Optional[dict[str, str]] = None,
    ):
        # Ensure AGENT_DB / RHOBIND_RELEASE etc. point at the delivery package
        apply_delivery_env()
        self.root = delivery_root()
        self.offline = offline
        self.prefer_import = prefer_import
        self.device = device
        self.use_conda = use_conda
        self.conda_envs = {**DEFAULT_CONDA_ENV, **(conda_envs or {})}
        self.meta = tools_meta_by_name()
        # Idempotency: same tool+args within TTL returns prior envelope (skill anti-loop)
        self._dedupe_ttl_s = 90.0
        self._recent_calls: dict[str, tuple[float, dict[str, Any]]] = {}

    def script_path(self, name: str) -> Path:
        """Map registry tool name to an absolute script path (raises if missing)."""
        rel = SCRIPT_MAP.get(name)
        if not rel:
            raise KeyError(
                f"No validated mapping.yaml script binding for tool {name!r}. "
                f"Reconcile mapping.yaml with tools/registry.json."
            )
        p = (self.root / rel).resolve()
        if not p.is_file():
            raise FileNotFoundError(
                f"Delivery script missing for {name!r}: {p} "
                f"(DELIVERY_ROOT={self.root})"
            )
        return p

    def _args_hash(self, name: str, payload: dict[str, Any]) -> str:
        import hashlib
        import json

        blob = json.dumps({"tool": name, "payload": payload}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def _esm_cache_dir(self) -> Path:
        from app.core.paths import CACHE

        d = CACHE / "esm"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _esm_disk_get(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        import hashlib
        import json

        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        path = self._esm_cache_dir() / f"{key}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _esm_disk_put(self, payload: dict[str, Any], out: dict[str, Any]) -> None:
        import hashlib
        import json

        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        path = self._esm_cache_dir() / f"{key}.json"
        try:
            slim = {k: v for k, v in out.items() if not str(k).startswith("_") or k == "ok"}
            path.write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def call(self, name: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """
        Call delivery tool ``name``.

        Decision order
        --------------
        0. axes hard-gate (runtime_config) → skipped envelope
        1. ``offline=True`` and registry ``network=true`` → skip (no fabricated result)
        1b. same args within TTL → return prior result (``_deduped``)
        2. GPU tool with no ``device`` in payload → fill ``self.device``
        3. pure-Python and ``prefer_import`` → ``_call_import`` (``run()``)
        4. otherwise → ``_call_subprocess`` (CLI ``--json``)
        """
        payload = dict(payload or {})
        t0 = time.perf_counter()

        try:
            from app.backends.delivery.stage_tools import axis_enabled

            ok_axis, blocked = axis_enabled(name)
            if not ok_axis:
                try:
                    from nanobot.agent.tools.rbp.turn_guards import add_evidence_flag

                    if blocked == "structure":
                        add_evidence_flag("structure_axis_unavailable", True)
                        add_evidence_flag("structure_axis_skipped", True)
                    elif blocked == "use_af3":
                        add_evidence_flag("af3_axis_skipped", True)
                    elif blocked:
                        add_evidence_flag(f"axis_{blocked}_skipped", True)
                except Exception:
                    pass
                return {
                    "ok": False,
                    "skipped": True,
                    "tool": name,
                    "error": f"axis {blocked!r} disabled in runtime_config; refuse {name}",
                    "_latency_ms": 0.0,
                    "_invocation": "skipped_axis",
                }
        except Exception:
            pass

        meta = self.meta.get(name, {})

        # ``structure_fetch`` is registry-marked network because it can download,
        # but it is local-first. In offline mode execute it with downloading
        # disabled so bundled AFDB models remain scientifically usable.
        if self.offline and name == "structure_fetch":
            payload["allow_download"] = False
        # Other network tools fail closed; never fabricate a cached-looking result.
        elif self.offline and meta.get("network"):
            return {
                "ok": False,
                "skipped": True,
                "tool": name,
                "error": f"offline=true; tool {name!r} requires network (registry flag)",
                "_latency_ms": 0.0,
                "_invocation": "skipped_offline",
            }

        ah = self._args_hash(name, payload)
        now = time.time()

        # Persistent disk cache for expensive ESM similarity (domain cache, not SDK).
        if name == "esm_similarity":
            disk = self._esm_disk_get(payload)
            if disk is not None:
                out = dict(disk)
                out["_deduped"] = True
                out["_cache"] = "esm_disk"
                out["_args_hash"] = ah
                out["_latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
                return out

        prev = self._recent_calls.get(ah)
        if prev is not None:
            ts, cached = prev
            if now - ts <= self._dedupe_ttl_s:
                out = dict(cached)
                out["_deduped"] = True
                out["_args_hash"] = ah
                out["_latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
                return out

        if meta.get("gpu") and "device" not in payload:
            payload["device"] = self.device

        try:
            if self.prefer_import and name in PURE_PYTHON_TOOLS:
                out = self._call_import(name, payload)
                invocation = "import_run"
            else:
                out = self._call_subprocess(name, payload)
                invocation = "subprocess_json"

            if not isinstance(out, dict):
                out = {"value": out}
            # Preserve delivery ``ok`` semantics; default True only if absent
            out.setdefault("ok", True)
            out["_tool"] = name
            out["_script"] = str(self.script_path(name))
            out["_invocation"] = invocation
            out["_args_hash"] = ah
            out["_latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
            self._recent_calls[ah] = (now, dict(out))
            if name == "esm_similarity" and out.get("ok", True) and not out.get("skipped"):
                self._esm_disk_put(payload, out)
            return out

        except Exception as e:  # noqa: BLE001 — return envelope, do not crash agent
            err = {
                "ok": False,
                "tool": name,
                "error": f"{type(e).__name__}: {e}",
                "_script": SCRIPT_MAP.get(name),
                "_invocation": "failed",
                "_args_hash": ah,
                "_latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            }
            self._recent_calls[ah] = (now, dict(err))
            return err

    # ------------------------------------------------------------------
    # (B) In-process: import delivery ``run(payload)``
    # ------------------------------------------------------------------
    def _call_import(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Equivalent to::

            # on the delivery side
            sys.path.insert(0, "agent/tools")
            sys.path.insert(0, "agent/tools/<category>")
            # then load <name>.py and call run(payload)

        Many delivery tools do ``from _common import ...``, so ``agent/tools``
        is inserted on ``sys.path``.
        """
        script = self.script_path(name)
        tools_root = self.root / "agent" / "tools"
        for p in (str(tools_root), str(script.parent)):
            if p not in sys.path:
                sys.path.insert(0, p)

        # Load by file path to avoid clashing with same-named App modules
        mod_name = f"delivery_tool_{name}"
        spec = importlib.util.spec_from_file_location(mod_name, script)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec for {script}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)

        if hasattr(mod, "run") and callable(mod.run):
            return mod.run(payload)
        # Some delivery tools expose no run(payload) and a non-JSON CLI (e.g.
        # colabfold_msa uses get_msa()/--seq). Adapt those without editing delivery.
        adapter = _IMPORT_ADAPTERS.get(name)
        if adapter is not None:
            return adapter(mod, payload)
        raise AttributeError(
            f"{script} has no callable run(payload) — not a delivery tool"
        )

    # ------------------------------------------------------------------
    # (A) CLI: python script --json '...'
    # ------------------------------------------------------------------
    def _call_subprocess(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Equivalent shell::

            source agent/setup.sh
            conda run -n protein_embed python agent/tools/sequence/esm_similarity.py \\
                --json '{"sequence":"...","encoder":"esmc","device":"cuda"}'

        The child inherits env vars from ``apply_delivery_env()`` so
        ``_common.py`` resolves ``AGENT_DB`` / ``EMB_BANK`` correctly.
        """
        script = self.script_path(name)
        apply_delivery_env()
        env = self._subprocess_env()

        conda_env = self.conda_envs.get(name) if self.use_conda else None
        json_arg = json.dumps(payload, ensure_ascii=False)

        # Prefer the env's absolute python binary over `conda run … python`.
        # The agent .venv has torch but NOT transformers; if PATH/.venv leaks
        # into the child, rhobind_predict fails with exactly:
        #   ModuleNotFoundError: No module named 'transformers'
        py = self._conda_python(conda_env) if conda_env else None
        # AF3 on Blackwell (RTX 5090 / CC12): prefer explicit AF3_PYTHON, then
        # af3_blackwell, then classic af3. Delivery maps this tool to env name
        # "af3", which cannot run inference on CC12.
        if name == "structure_predict_af3":
            af3_override = (os.environ.get("AF3_PYTHON") or "").strip()
            if af3_override and Path(af3_override).is_file():
                py = Path(af3_override)
                conda_env = "af3_blackwell" if "af3_blackwell" in af3_override else (conda_env or "af3")
            else:
                bw = self._conda_python("af3_blackwell")
                if bw is not None:
                    py = bw
                    conda_env = "af3_blackwell"
        if py is not None:
            cmd = [str(py), str(script), "--json", json_arg]
            # Point CONDA_PREFIX at the science env so native libs resolve.
            prefix = py.parent.parent
            env["CONDA_PREFIX"] = str(prefix)
            env["CONDA_DEFAULT_ENV"] = conda_env or ""
            # Direct env python (vs `conda run`) does not put env bin on PATH.
            # foldseek / mmseqs / USalign are invoked by basename in delivery
            # scripts → must prepend ``$CONDA_PREFIX/bin``.
            env["PATH"] = f"{prefix / 'bin'}:{env.get('PATH', '')}"
            foldseek = prefix / "bin" / "foldseek"
            if foldseek.is_file():
                env["FOLDSEEK"] = str(foldseek)
            mmseqs = prefix / "bin" / "mmseqs"
            if mmseqs.is_file():
                env.setdefault("MMSEQS", str(mmseqs))
            # USalign often lives in AGENT_DB/bin (set by setup.sh)
            us = env.get("USALIGN") or ""
            if us and Path(us).is_file():
                env["USALIGN"] = us
        else:
            # Without conda, still run for real; missing deps → rc!=0 (recorded upstream).
            # No synthetic AUPRC / binding probabilities.
            cmd = [sys.executable, str(script), "--json", json_arg]

        # Pin mmseqs search threads via App shim (do not edit delivery scripts).
        if name in _MMSEQS_THREAD_TOOLS and _MMSEQS_WRAP.is_file():
            real = env.get("MMSEQS") or "mmseqs"
            if real != str(_MMSEQS_WRAP):
                env["MMSEQS_REAL"] = real
            env["MMSEQS"] = str(_MMSEQS_WRAP)
            env["MMSEQS_THREADS"] = env.get("OMP_NUM_THREADS") or "4"

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(payload.get("timeout_s") or 3600),
            env=env,
            cwd=str(self.root),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"delivery tool {name!r} failed rc={proc.returncode}\n"
                f"cmd={' '.join(cmd[:6])}...\n"
                f"stderr={proc.stderr[-4000:]}\n"
                f"stdout={proc.stdout[-1500:]}"
            )
        return self._parse_json_stdout(proc.stdout)

    @staticmethod
    def _omp_ok(v: str | None) -> bool:
        return bool(v) and v.isdigit() and int(v) > 0

    @classmethod
    def _subprocess_env(cls) -> dict[str, str]:
        """Env for science-tool children: keep delivery vars, drop agent venv leak."""
        env = os.environ.copy()

        # Agent .venv on PATH / VIRTUAL_ENV can make children see torch without
        # transformers (exact rhobind_predict failure mode). Strip those.
        env.pop("VIRTUAL_ENV", None)
        env.pop("VIRTUAL_ENV_PROMPT", None)
        env.pop("PYTHONHOME", None)

        # Keep delivery/HF vars; drop agent PYTHONPATH so site-packages win.
        env.pop("PYTHONPATH", None)

        path = env.get("PATH", "")
        if path:
            cleaned = [
                p
                for p in path.split(":")
                if p and "/.venv/" not in p and not p.endswith("/.venv/bin")
            ]
            env["PATH"] = ":".join(cleaned)

        if not cls._omp_ok(env.get("OMP_NUM_THREADS")):
            env["OMP_NUM_THREADS"] = "4"
        if not cls._omp_ok(env.get("MKL_NUM_THREADS")):
            env["MKL_NUM_THREADS"] = env["OMP_NUM_THREADS"]
        if not cls._omp_ok(env.get("OPENBLAS_NUM_THREADS")):
            env["OPENBLAS_NUM_THREADS"] = env["OMP_NUM_THREADS"]
        return env

    @classmethod
    def _conda_python(cls, name: str) -> Optional[Path]:
        """Absolute ``…/envs/<name>/bin/python`` if that conda env exists."""
        prefix = cls._conda_env_prefix(name)
        if prefix is None:
            return None
        py = prefix / "bin" / "python"
        return py if py.is_file() else None

    @staticmethod
    def _conda_env_prefix(name: str) -> Optional[Path]:
        # Fast path: CONDA_ENVS_PATH / common local layouts (no host-specific paths)
        envs_roots: list[Path] = []
        for key in ("CONDA_ENVS_PATH", "CONDA_ENVS_DIRS"):
            raw = os.environ.get(key) or ""
            for part in raw.split(os.pathsep):
                if part.strip():
                    envs_roots.append(Path(part.strip()))
        for base in (
            os.environ.get("CONDA_PREFIX"),
            os.environ.get("MAMBA_ROOT_PREFIX"),
            os.path.expanduser("~/miniconda3"),
            os.path.expanduser("~/anaconda3"),
            os.path.expanduser("~/mambaforge"),
            os.path.expanduser("~/miniforge3"),
        ):
            if base:
                envs_roots.append(Path(base) / "envs")
                # When CONDA_PREFIX is an env itself, sibling envs live next door
                p = Path(base)
                if p.name != "envs" and (p.parent / "envs").is_dir():
                    envs_roots.append(p.parent / "envs")
        for root in envs_roots:
            cand = root / name
            if (cand / "bin" / "python").is_file():
                return cand
        try:
            r = subprocess.run(
                ["conda", "env", "list"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode != 0:
                return None
            for line in r.stdout.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                if parts and parts[0] == name:
                    # `name /path` or `name * /path`
                    path = parts[-1]
                    p = Path(path)
                    if (p / "bin" / "python").is_file():
                        return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return None

    @staticmethod
    def _parse_json_stdout(text: str) -> dict[str, Any]:
        """Parse JSON from tool stdout (tolerates leading log lines)."""
        text = (text or "").strip()
        if not text:
            raise ValueError("empty tool stdout")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.rfind("{")
            if start < 0:
                raise ValueError(f"no JSON object in stdout: {text[:500]!r}")
            return json.loads(text[start:])
