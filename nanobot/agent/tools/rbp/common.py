# -*- coding: utf-8 -*-
"""Shared helpers for curated RBP agent tools (SoT: this file).

This module does **not** compute scientific scores. It does not implement
RhoBind, Foldseek, ESM, or literature retrieval. Responsibilities:

* Locate the ``nanobot-bio`` package root and ensure ``app`` is on ``sys.path``
* Obtain a ``DeliveryToolClient`` for read-only calls into delivery scripts
* Resolve compute device (``cuda`` / ``cpu``), protein sequences, structure paths
* Build tool return envelopes (``ok`` / ``err``) and JSON ``dumps``
* Cross-cutting caches (structure / literature) and catalogue FASTA helpers

Invariant: probs, similarities, and sequences come from delivery or upstream
tool results. This file is orchestration glue only.

CLI examples:
  nanobot-bio doctor
  python -m app.sync_overlay
  nanobot-bio nanobot-smoke
  source scripts/nbio.sh
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional


def ensure_nanobot_bio_on_path() -> Path:
    """Locate nanobot-bio root and put it on sys.path."""
    env = os.environ.get("NANOBOT_BIO_ROOT")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    # .../nanobot-bio/nanobot/agent/tools/rbp/common.py
    if len(here.parents) > 4:
        candidates.append(here.parents[4])  # nanobot-bio
    if len(here.parents) > 3:
        nb_pkg = here.parents[3]  # .../nanobot
        candidates.append(nb_pkg.parent)  # nanobot-bio
        candidates.append(nb_pkg.parent.parent / "nanobot-bio")
    bio = os.environ.get("BIO_ROOT")
    if bio:
        candidates.append(Path(bio) / "nanobot-bio")
        candidates.append(Path(bio))

    def _is_bio_root(c: Path) -> bool:
        return (c / "app" / "backends" / "delivery" / "client.py").is_file() or (
            c / "backends" / "delivery" / "client.py"
        ).is_file()

    for c in candidates:
        try:
            c = c.resolve()
        except OSError:
            continue
        if _is_bio_root(c):
            if str(c) not in sys.path:
                sys.path.append(str(c))
            os.environ.setdefault("NANOBOT_BIO_ROOT", str(c))
            return c
    raise FileNotFoundError(
        "Cannot find nanobot-bio (app/backends/delivery). "
        "Set NANOBOT_BIO_ROOT=/path/to/nanobot-bio"
    )


_CUDA_CACHE: Optional[bool] = None


def _nvidia_visible() -> bool:
    """Fast GPU probe without importing torch (chat startup path)."""
    if os.path.exists("/dev/nvidia0"):
        return True
    try:
        import shutil
        import subprocess

        if not shutil.which("nvidia-smi"):
            return False
        r = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0 and bool((r.stdout or b"").strip())
    except Exception:
        return False


def _rhobind_torch_cuda() -> Optional[bool]:
    """Whether the rhobind conda env's torch can use CUDA (None if unknown)."""
    try:
        from app.backends.delivery.client import DeliveryToolClient

        py = DeliveryToolClient._conda_python("rhobind")
        if py is None:
            return None
        import subprocess

        r = subprocess.run(
            [str(py), "-c", "import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)"],
            capture_output=True,
            timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return None


def cuda_available(*, force_refresh: bool = False, allow_torch: bool = False) -> bool:
    """True when a CUDA device is usable for RhoBind / ESM delivery tools.

    Prefer ``nvidia-smi`` / ``/dev/nvidia0`` so agent startup does not pay for
    ``import torch`` (~1.5s). When a GPU is visible, also check the ``rhobind``
    env's torch (CPU wheels report False) so ``auto`` does not force ``cuda``.
    Torch in the *current* interpreter is only used when ``allow_torch=True``
    and the fast probe is inconclusive.

    Result is cached for the process. Set ``RHOBIND_FORCE_CPU=1`` in tests.
    """
    global _CUDA_CACHE
    if os.environ.get("RHOBIND_FORCE_CPU", "").strip().lower() in ("1", "true", "yes"):
        return False
    if _CUDA_CACHE is not None and not force_refresh:
        return _CUDA_CACHE

    ok = _nvidia_visible()
    if ok:
        rh = _rhobind_torch_cuda()
        if rh is False:
            ok = False
    if not ok and allow_torch:
        try:
            import torch  # type: ignore

            ok = bool(torch.cuda.is_available())
        except Exception:
            ok = False

    _CUDA_CACHE = ok
    return ok


def resolve_device(requested: Optional[str] = None) -> str:
    """Resolve compute device for delivery tools.

    Ideal product default is **CUDA when available** (HANDOFF / BUILD_SPEC).
    Accepted values: ``auto`` | ``cuda`` | ``cpu`` | empty (→ env / auto).

    Does **not** import torch on the hot path (chat / RBPAgent init).
    """
    raw = (requested if requested is not None else os.environ.get("RHOBIND_DEVICE", "auto"))
    raw = str(raw or "auto").strip().lower()
    if raw in ("cuda", "gpu"):
        return "cuda"
    if raw == "cpu":
        return "cpu"
    if raw in ("", "auto", "default"):
        return "cuda" if cuda_available(allow_torch=False) else "cpu"
    # Unknown token — still prefer CUDA in ideal envs.
    return "cuda" if cuda_available(allow_torch=False) else "cpu"


def get_delivery_client(
    *,
    offline: bool = False,
    device: Optional[str] = None,
    use_conda: bool = True,
):
    ensure_nanobot_bio_on_path()
    from app.backends.delivery.client import DeliveryToolClient
    from app.backends.delivery.env import apply_delivery_env

    apply_delivery_env()
    return DeliveryToolClient(
        offline=offline,
        device=resolve_device(device),
        use_conda=use_conda,
    )


def get_runtime_config(*, prefer_evolved: bool = True) -> dict[str, Any]:
    """Injectable facade for Table-3 / axes config (keeps tools off direct app imports)."""
    ensure_nanobot_bio_on_path()
    from app.core.runtime_config import load_runtime_config

    return load_runtime_config(prefer_evolved=prefer_evolved)


def axis_tool_enabled(tool_name: str, axes: Optional[dict] = None) -> tuple[bool, Optional[str]]:
    ensure_nanobot_bio_on_path()
    from app.backends.delivery.stage_tools import axis_enabled

    return axis_enabled(tool_name, axes)


def apply_delivery_env_facade() -> None:
    ensure_nanobot_bio_on_path()
    from app.backends.delivery.env import apply_delivery_env

    apply_delivery_env()


def load_rbp_registry_facade() -> Any:
    ensure_nanobot_bio_on_path()
    from app.backends.delivery.env import load_rbp_registry

    return load_rbp_registry()


def is_near_match_score_facade(score: Any, *, threshold: Optional[float] = None) -> bool:
    ensure_nanobot_bio_on_path()
    from app.core.verdict_schema import is_near_match_score

    if threshold is None:
        return bool(is_near_match_score(score))
    return bool(is_near_match_score(score, threshold=threshold))


def structure_cache_dir() -> Path:
    ensure_nanobot_bio_on_path()
    from app.core.paths import STRUCTURE_CACHE, ensure_artifact_dirs

    ensure_artifact_dirs()
    return Path(STRUCTURE_CACHE)


def package_root_dir() -> Path:
    ensure_nanobot_bio_on_path()
    from app.core.paths import PACKAGE_ROOT

    return Path(PACKAGE_ROOT)


def fusion_weights_facade() -> dict[str, Any]:
    ensure_nanobot_bio_on_path()
    from app.core.runtime_config import fusion_weights

    return dict(fusion_weights() or {})


def tau_drop_facade() -> float:
    ensure_nanobot_bio_on_path()
    from app.core.runtime_config import tau_drop as _tau

    return float(_tau())


def config_source_facade() -> str:
    ensure_nanobot_bio_on_path()
    from app.core.runtime_config import config_source

    return str(config_source())


def catalogue_fasta_path() -> Optional[Path]:
    """Bundled all_rbps.fasta under delivery reference/ (read-only)."""
    roots: list[Path] = []
    for key in ("RBP_PROTEINS", "DELIVERY_ROOT", "BUNDLE_ROOT"):
        v = os.environ.get(key)
        if v:
            roots.append(Path(v))
    dr = os.environ.get("DELIVERY_ROOT")
    if dr:
        roots.append(Path(dr) / "reference")
    for r in roots:
        for cand in (
            r / "sequences" / "all_rbps.fasta",
            r / "reference" / "sequences" / "all_rbps.fasta",
        ):
            if cand.is_file():
                return cand
    return None


def load_catalogue_sequence(query: str) -> Optional[str]:
    """Load protein sequence for alias/UniProt from delivery ``all_rbps.fasta``.

    Headers look like ``>YTHDF2|Q9Y5A9|YTHDF2|len=579``.
    """
    q = (query or "").strip()
    if not q:
        return None
    fasta = catalogue_fasta_path()
    if fasta is None:
        return None
    q_up = q.upper()
    cur_hdr = ""
    chunks: list[str] = []
    try:
        with open(fasta, encoding="utf-8") as f:
            for line in f:
                if line.startswith(">"):
                    if cur_hdr and chunks:
                        parts = cur_hdr[1:].split("|")
                        keys = {p.strip().upper() for p in parts if p.strip()}
                        if q_up in keys:
                            return "".join(chunks).upper()
                    cur_hdr = line.strip()
                    chunks = []
                else:
                    chunks.append(line.strip())
            if cur_hdr and chunks:
                parts = cur_hdr[1:].split("|")
                keys = {p.strip().upper() for p in parts if p.strip()}
                if q_up in keys:
                    return "".join(chunks).upper()
    except OSError:
        return None
    return None


def find_exact_catalogue_entry(sequence: str) -> Optional[dict[str, str]]:
    """Return ``{alias, uniprot}`` when ``sequence`` exactly equals a catalogue AA.

    Used by Stage-0 near-known: masked MMseqs can under-report identity on
    low-complexity catalogue proteins (e.g. PTBP1 self-hit ~0.93), so an exact
    FASTA equality check is stronger provenance than the alignment score.
    """
    seq = (sequence or "").strip().upper().replace(" ", "").replace("\n", "")
    if len(seq) < 20:
        return None
    fasta = catalogue_fasta_path()
    if fasta is None:
        return None
    cur_hdr = ""
    chunks: list[str] = []

    def _maybe(hdr: str, body: list[str]) -> Optional[dict[str, str]]:
        if not hdr or not body:
            return None
        cat = "".join(body).upper()
        if cat != seq:
            return None
        parts = [p.strip() for p in hdr[1:].split("|") if p.strip()]
        alias = parts[0] if parts else ""
        uniprot = parts[1] if len(parts) > 1 else ""
        if not alias and not uniprot:
            return None
        return {"alias": alias or uniprot, "uniprot": uniprot or alias}

    try:
        with open(fasta, encoding="utf-8") as f:
            for line in f:
                if line.startswith(">"):
                    hit = _maybe(cur_hdr, chunks)
                    if hit:
                        return hit
                    cur_hdr = line.strip()
                    chunks = []
                else:
                    chunks.append(line.strip())
            return _maybe(cur_hdr, chunks)
    except OSError:
        return None


def looks_like_accession_or_alias(text: str) -> bool:
    """True if ``text`` is a UniProt/gene token, not a protein AA string."""
    s = (text or "").strip()
    if not s or len(s) > 32 or any(ch.isspace() for ch in s):
        return False
    # UniProt accession (e.g. O43251, Q9Y5A9, P26599, A0A0B4J2F0)
    import re

    if re.fullmatch(r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}", s, re.I):
        return True
    # Gene / alias tokens (RBFOX2, PTBP1) — short, no digits-only, mostly alnum
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{1,24}", s) and any(c.isalpha() for c in s):
        # Reject obvious AA peptides (high fraction of valid AA letters, length>=20 handled elsewhere)
        if len(s) <= 15:
            return True
    return False


def looks_like_rna(seq: str) -> bool:
    s = (seq or "").strip().upper().replace(" ", "")
    if len(s) < 8:
        return False
    return set(s) <= set("ACGTUN")


def looks_like_dummy_protein(seq: str) -> bool:
    """Detect invented poly-X / poly-A junk the LLM sometimes fabricates."""
    s = (seq or "").strip().upper().replace(" ", "")
    if len(s) < 20:
        return False
    from collections import Counter

    c = Counter(s)
    top_n, top_cnt = c.most_common(1)[0]
    if top_cnt / len(s) >= 0.85 and top_n in "ACDEFGHIKLMNPQRSTVWY":
        return True
    return False


def fetch_uniprot_sequence(accession: str, *, timeout: float = 25.0) -> Optional[str]:
    """Fetch AA sequence from UniProt REST FASTA (agent-side; does not edit delivery)."""
    import re
    import time
    import urllib.error
    import urllib.request

    acc = (accession or "").strip().upper()
    if not re.fullmatch(
        r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}",
        acc,
    ):
        return None
    url = f"https://rest.uniprot.org/uniprotkb/{acc}.fasta"
    last_err: Optional[BaseException] = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            lines = [
                ln.strip()
                for ln in text.splitlines()
                if ln.strip() and not ln.startswith(">")
            ]
            seq = "".join(lines).upper()
            if len(seq) >= 20:
                return seq
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt == 0:
                time.sleep(0.6)
    del last_err
    return None


def resolve_protein_sequence(kwargs: dict[str, Any]) -> tuple[str, Optional[str]]:
    """Resolve AA sequence from kwargs.

    Returns ``(sequence, source)`` where source is
    ``sequence`` | ``catalogue`` | ``uniprot_rest`` | None.
    If ``sequence``/``target_sequence`` is actually an accession/alias, load FASTA
    (or UniProt REST for accessions outside the RBP catalogue).
    """
    raw = (kwargs.get("sequence") or kwargs.get("target_sequence") or "").strip()
    if raw and looks_like_accession_or_alias(raw):
        loaded = load_catalogue_sequence(raw)
        if loaded:
            return loaded, "catalogue"
        # UniProt accession outside catalogue → REST (never treat ID as AA)
        rest = fetch_uniprot_sequence(raw)
        if rest:
            return rest, "uniprot_rest"
        return "", None
    if raw and looks_like_rna(raw):
        return "", None
    if raw and looks_like_dummy_protein(raw):
        return "", None
    if raw and len(raw) >= 20:
        return raw.upper(), "sequence"

    for key in ("alias", "uniprot", "query", "rbp_id", "name"):
        q = kwargs.get(key)
        if not q:
            continue
        q = str(q).strip()
        loaded = load_catalogue_sequence(q)
        if loaded:
            return loaded, "catalogue"
        rest = fetch_uniprot_sequence(q)
        if rest:
            return rest, "uniprot_rest"
    return (raw.upper() if raw and len(raw) >= 20 else ""), None


def not_in_catalogue_hint(*ids: str) -> str:
    """Short reason when tools fail because the protein is outside RhoBind K."""
    shown = "/".join(x for x in ids if x) or "this protein"
    return (
        f"{shown} is not in the RhoBind RBP catalogue (~238). "
        "seq/struct catalogue tools need a real AA `sequence` (auto-fetched from "
        "UniProt when you pass a valid accession), or abstain with p_hat=null / "
        "confidence=low. Do not invent sequences or loop AF3."
    )


_STRUCTURE_EXTS = (".pdb", ".pdb.gz", ".cif", ".mmcif", ".mcif", ".ent")


def resolve_structure_file(structure_file: str) -> tuple[Optional[Path], Optional[str]]:
    """Validate a local PDB/CIF path supplied as an RBP input modality (A1).

    Returns ``(resolved_path, error_reason)``. On success ``error_reason`` is None
    and ``resolved_path`` points to an existing file with a recognised structure
    extension under an allowlisted root (same jail as FASTA/doc tools).
    """
    s = (structure_file or "").strip()
    if not s:
        return None, None
    p = Path(s).expanduser()
    if not p.is_absolute():
        # Reject relative paths to avoid surprising the workspace scope.
        return None, "structure_file must be an absolute path"
    if not p.name.lower().endswith(_STRUCTURE_EXTS):
        return None, (
            f"structure_file must be one of {', '.join(_STRUCTURE_EXTS)} "
            "(matching the filename suffix); "
            f"got {p.name}"
        )
    try:
        from nanobot.agent.tools.rbp.path_guard import resolve_allowed_path

        resolved = resolve_allowed_path(
            p,
            allowed_suffixes={
                ".pdb",
                ".cif",
                ".mmcif",
                ".mcif",
                ".ent",
                ".gz",  # *.pdb.gz matched via name.endswith above; suffix may be .gz
            },
        )
    except ValueError as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001
        return None, f"structure_file allowlist error: {type(e).__name__}: {e}"
    # Double-check compound suffixes like .pdb.gz (suffix alone is .gz).
    name_l = resolved.name.lower()
    if not name_l.endswith(_STRUCTURE_EXTS):
        return None, (
            f"structure_file must be one of {', '.join(_STRUCTURE_EXTS)}; "
            f"got {resolved.name}"
        )
    return resolved, None


def catalogue_pdb_path(*, uniprot: str = "", alias: str = "") -> Optional[Path]:
    """Resolve AFDB PDB under ``AFDB_DIR`` (``ALIAS_UNIPROT.pdb``)."""
    afdb = os.environ.get("AFDB_DIR")
    if not afdb:
        return None
    root = Path(afdb)
    if not root.is_dir():
        return None
    u = (uniprot or "").strip()
    a = (alias or "").strip()
    cands: list[Path] = []
    if a and u:
        cands.append(root / f"{a}_{u}.pdb")
    if u:
        cands.extend(root.glob(f"*_{u}.pdb"))
        cands.append(root / f"{u}.pdb")
    if a:
        cands.extend(root.glob(f"{a}_*.pdb"))
    for p in cands:
        if p.is_file():
            return p
    return None


def _structure_cache_dir() -> Path:
    try:
        root = ensure_nanobot_bio_on_path()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from app.core.paths import STRUCTURE_CACHE, ensure_artifact_dirs

        ensure_artifact_dirs()
        return STRUCTURE_CACHE
    except Exception:
        fallback = (
            Path(os.environ.get("NANOBOT_ARTIFACTS", Path.home() / ".nanobot-bio" / "artifacts"))
            / "cache"
            / "structure"
        )
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def structure_cache_get(key: str, *, ttl_s: float = 7 * 24 * 3600) -> Optional[dict[str, Any]]:
    """Return cached structure-tool payload if fresh (success or failure)."""
    import hashlib

    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    path = _structure_cache_dir() / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = float(data.get("ts") or 0)
        if time.time() - ts > float(ttl_s):
            return None
        return data.get("payload")
    except Exception:
        return None


def structure_cache_put(key: str, payload: dict[str, Any]) -> None:
    """Disk-cache AF3/structure results (including failures) to avoid 200s+ repeats."""
    import hashlib

    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    path = _structure_cache_dir() / f"{safe}.json"
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "key": key, "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _literature_cache_dir() -> Path:
    try:
        root = ensure_nanobot_bio_on_path()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from app.core.paths import LITERATURE_CACHE, ensure_artifact_dirs

        ensure_artifact_dirs()
        return LITERATURE_CACHE
    except Exception:
        fallback = (
            Path(os.environ.get("NANOBOT_ARTIFACTS", Path.home() / ".nanobot-bio" / "artifacts"))
            / "cache"
            / "literature"
        )
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def literature_cache_get(key: str, *, ttl_s: float = 7 * 24 * 3600) -> Optional[dict[str, Any]]:
    """Return cached literature_search payload if fresh (A6 cross-session TTL memo)."""
    import hashlib

    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    path = _literature_cache_dir() / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = float(data.get("ts") or 0)
        if time.time() - ts > float(ttl_s):
            return None
        return data.get("payload")
    except Exception:
        return None


def literature_cache_put(key: str, payload: dict[str, Any]) -> None:
    """Disk-cache literature_search results (cross-session TTL memo, A6)."""
    import hashlib

    safe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    path = _literature_cache_dir() / f"{safe}.json"
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "key": key, "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def ok(value: Any, latency_ms: float = 0.0) -> dict[str, Any]:
    return {"status": "ok", "value": value, "latency_ms": round(float(latency_ms), 3)}


def err(reason: str, latency_ms: float = 0.0) -> dict[str, Any]:
    return {"status": "error", "reason": str(reason), "latency_ms": round(float(latency_ms), 3)}


def timed_call(fn: Callable[[], Any]) -> tuple[Any, float, str | None]:
    t0 = time.perf_counter()
    try:
        v = fn()
        return v, (time.perf_counter() - t0) * 1000.0, None
    except Exception as e:  # noqa: BLE001
        return None, (time.perf_counter() - t0) * 1000.0, f"{type(e).__name__}: {e}"
