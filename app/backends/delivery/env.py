"""Resolve DELIVERY_ROOT and key paths without modifying delivery code."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# Tests may install pytest.skip here so missing delivery skips instead of fails.
_delivery_missing_hook: Callable[[], None] | None = None


def try_delivery_root() -> Path | None:
    """Return rhobind_agent_delivery root if present, else None.

    Unlike ``delivery_root()``, never raises. An explicit ``DELIVERY_ROOT`` that
    does not exist is treated as missing (returns None).
    """
    env = os.environ.get("DELIVERY_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_dir() else None
    # Default: sibling of nanobot-bio under bio_agent/
    here = Path(__file__).resolve()
    # .../nanobot-bio/app/backends/delivery/env.py → parents[4] = bio_agent
    candidate = here.parents[4] / "rhobind_agent_delivery"
    if candidate.is_dir():
        return candidate.resolve()
    # Legacy layout (backends at repo root)
    legacy = here.parents[3] / "rhobind_agent_delivery"
    if legacy.is_dir():
        return legacy.resolve()
    return None


def delivery_root() -> Path:
    """Package root of rhobind_agent_delivery.

    Raises ``FileNotFoundError`` when unset and no sibling bundle exists.
    When a ``_delivery_missing_hook`` is installed (pytest conftest), the hook
    runs first so CI without delivery can skip rather than fail.
    """
    found = try_delivery_root()
    if found is not None:
        return found
    # Preserve historical behavior: explicit DELIVERY_ROOT wins even if missing
    # (callers then fail on the concrete path).
    env = os.environ.get("DELIVERY_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if _delivery_missing_hook is not None:
        _delivery_missing_hook()
    raise FileNotFoundError(
        "DELIVERY_ROOT not set and sibling rhobind_agent_delivery not found. "
        "export DELIVERY_ROOT=/path/to/rhobind_agent_delivery"
    )


def resolve_delivery_paths() -> dict[str, Path]:
    root = delivery_root()
    return {
        "delivery_root": root,
        "tools_root": root / "agent" / "tools",
        "registry_json": root / "agent" / "tools" / "registry.json",
        "predict_api": root / "agent" / "backbone" / "predict_api.py",
        "agent_db": Path(os.environ.get("AGENT_DB", root / "agent_db")),
        "rbp_registry": Path(
            os.environ.get(
                "RBP_REGISTRY",
                root / "agent_db" / "registry" / "rbp_registry.json",
            )
        ),
        "rhobind_release": Path(
            os.environ.get(
                "RHOBIND_RELEASE",
                root / "release" / "rhobind_release_v1",
            )
        ),
        "setup_sh": root / "agent" / "setup.sh",
        "examples": root / "agent" / "examples",
    }


@lru_cache(maxsize=1)
def load_rbp_registry() -> dict[str, Any]:
    paths = resolve_delivery_paths()
    reg_path = paths["rbp_registry"]
    if not reg_path.is_file():
        raise FileNotFoundError(f"RBP registry not found: {reg_path}")
    with open(reg_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("rbp_registry.json must be a dict keyed by UniProt")
    return data


def conda_env_python(name: str) -> Optional[Path]:
    """Absolute ``…/envs/<name>/bin/python`` if that conda env exists.

    Standalone resolver (no import of client.py, to avoid a circular import).
    Mirrors ``DeliveryToolClient._conda_env_prefix`` fast path + ``conda env list``.
    """
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
            p = Path(base)
            if p.name != "envs" and (p.parent / "envs").is_dir():
                envs_roots.append(p.parent / "envs")
    for root in envs_roots:
        py = root / name / "bin" / "python"
        if py.is_file():
            return py
    try:
        r = subprocess.run(
            ["conda", "env", "list"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                if parts and parts[0] == name:
                    py = Path(parts[-1]) / "bin" / "python"
                    if py.is_file():
                        return py
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


@lru_cache(maxsize=8)
def _binary_runs(path: str) -> bool:
    """True if ``path`` is an executable that actually launches on this host.

    Prebuilt binaries (e.g. USalign) can be present but ABI-incompatible with the
    host glibc/libstdc++; running them yields a 'version GLIBC... not found' error.
    """
    if not path or not os.path.exists(path):
        return False
    try:
        r = subprocess.run([path], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    err = r.stderr or b""
    if b"not found" in err and (b"GLIBC" in err or b"GLIBCXX" in err):
        return False
    return True


def _default_hf_home() -> str:
    """Prefer ``HF_HOME``; else ``$XDG_CACHE_HOME/huggingface`` / ``~/.cache/huggingface``."""
    if os.environ.get("HF_HOME"):
        return str(Path(os.environ["HF_HOME"]).expanduser())
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return str(Path(xdg).expanduser() / "huggingface")
    return str(Path.home() / ".cache" / "huggingface")


def apply_delivery_env() -> dict[str, str]:
    """Set standard delivery env vars if missing (mirrors setup.sh defaults)."""
    root = delivery_root()
    hf_home = _default_hf_home()
    # Mirrors agent/setup.sh + AGENT_BUILD_SPEC §2
    defaults = {
        "DELIVERY_ROOT": str(root),
        "AGENT_DB": str(root / "agent_db"),
        "RBP_REGISTRY": str(root / "agent_db" / "registry" / "rbp_registry.json"),
        "RHOBIND_RELEASE": str(root / "release" / "rhobind_release_v1"),
        "RBP_PROTEINS": str(root / "reference"),
        "AFDB_DIR": str(root / "reference" / "structures" / "afdb"),
        "TRANSFER_DIR": str(root / "agent_db" / "transfer"),
        "EMB_BANK": str(root / "agent_db" / "embedding_bank"),
        "FOLDSEEK_DB": str(root / "agent_db" / "foldseek_db" / "refs"),
        "SEQ_DB": str(root / "agent_db" / "seq_db" / "refs"),
        "PEAKS_DB": str(root / "agent_db" / "peaks_db" / "peaks"),
        "USALIGN": str(root / "agent_db" / "bin" / "USalign"),
        "AF3_DIR": str(root / "agent" / "third_party" / "alphafold3"),
        "AF3_PARAMS": str(root / "af3_assets" / "alphafold_param"),
        # ESM / HF: AutoDL often cannot reach huggingface.co — use local cache + mirror
        "HF_HOME": hf_home,
        "HUGGINGFACE_HUB_CACHE": str(Path(hf_home) / "hub"),
        "TRANSFORMERS_CACHE": str(Path(hf_home) / "transformers"),
        "HF_ENDPOINT": "https://hf-mirror.com",
    }
    # AF3_PYTHON must be a conda interpreter with alphafold3 — NOT the agent .venv.
    # A complete isolated Blackwell stack wins over stale .env values unless the
    # operator explicitly sets AF3_FORCE_CLASSIC=1.
    bw_af3 = Path("/root/autodl-tmp/af3_blackwell/alphafold3")
    bw_py = conda_env_python("af3_blackwell")
    use_bw = (
        os.environ.get("AF3_FORCE_CLASSIC", "").strip().lower() not in {"1", "true", "yes"}
        and bw_py is not None
        and (bw_af3 / "run_alphafold.py").is_file()
    )
    if use_bw:
        os.environ["AF3_PYTHON"] = str(bw_py)
        os.environ["AF3_DIR"] = str(bw_af3)
        os.environ["AF3_CACHE"] = str(bw_af3.parent / "alphafold_cache")
        defaults["AF3_PYTHON"] = str(bw_py)
        defaults["AF3_DIR"] = str(bw_af3)
        defaults["AF3_CACHE"] = str(bw_af3.parent / "alphafold_cache")
    elif "AF3_PYTHON" not in os.environ:
        af3_py = conda_env_python("af3")
        if af3_py is not None:
            defaults["AF3_PYTHON"] = str(af3_py)
    applied = {}
    for k, v in defaults.items():
        if k not in os.environ:
            os.environ[k] = v
            applied[k] = v
        else:
            applied[k] = os.environ[k]
    Path(applied["HF_HOME"]).mkdir(parents=True, exist_ok=True)
    Path(applied["HUGGINGFACE_HUB_CACHE"]).mkdir(parents=True, exist_ok=True)
    Path(applied["TRANSFORMERS_CACHE"]).mkdir(parents=True, exist_ok=True)
    # If the USalign binary is present but ABI-incompatible (host glibc too old),
    # point USALIGN at a non-existent path so the delivery struct_align_usalign
    # tool takes its built-in foldseek TM-align fallback instead of silently
    # returning zero hits. Real USalign is preferred wherever it can execute.
    usalign = applied.get("USALIGN")
    if usalign and os.path.exists(usalign) and not _binary_runs(usalign):
        os.environ["USALIGN"] = usalign + ".unavailable"
        applied["USALIGN"] = os.environ["USALIGN"]
    # libgomp rejects OMP_NUM_THREADS=0 (and other non-positive/junk values) with a
    # noisy warning at import; some hosts inherit OMP_NUM_THREADS=0. Normalize the
    # agent's own process env so torch/numpy import cleanly. Subprocess science
    # tools are sanitized separately in client._subprocess_env.
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        val = os.environ.get(var)
        if val is not None and not (val.isdigit() and int(val) > 0):
            os.environ[var] = "4"
            applied[var] = "4"
    return applied
