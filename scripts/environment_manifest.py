#!/usr/bin/env python3
"""Write a reproducible science-environment and immutable-input manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _run(argv: list[str], *, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-500:],
    }


def _sha256(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "sha256": None, "size": None}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path),
        "exists": True,
        "sha256": digest.hexdigest(),
        "size": path.stat().st_size,
    }


def _python_probe(path: Path, imports: tuple[str, ...] = ()) -> dict[str, Any]:
    code = (
        "import importlib.metadata as m, json, platform; "
        f"names={list(imports)!r}; "
        "v=lambda n: next((d.version for d in m.distributions() "
        "if (d.metadata.get('Name') or '').lower()==n.lower()), None); "
        "print(json.dumps({'python':platform.python_version(),"
        "'packages':{n:v(n) for n in names}}))"
    )
    result = _run([str(path), "-c", code])
    if result.get("ok"):
        try:
            return {"executable": str(path), **json.loads(result["stdout"])}
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return {"executable": str(path), **result}


def build_manifest() -> dict[str, Any]:
    from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

    apply_delivery_env()
    paths = resolve_delivery_paths()
    delivery = Path(paths["delivery_root"])
    env_root = Path(os.environ.get("CONDA_ENVS_PATH") or "/root/autodl-tmp/conda/envs")
    registry = Path(paths["registry_json"])
    rbp_registry = Path(paths["rbp_registry"])
    release = Path(paths["rhobind_release"])
    immutable = [
        registry,
        rbp_registry,
        release / "README.md",
        release / "checkpoints" / "head_index_k562.json",
        release / "checkpoints" / "head_index_hepg2.json",
        release / "checkpoints" / "rhobind_k562_mt_all118_cutoff08.ckpt",
        release / "checkpoints" / "rhobind_hepg2_mt_all118_cutoff08.ckpt",
        delivery / "af3_assets" / "alphafold_param" / "af3.bin.zst",
    ]
    gpu = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,compute_cap,memory.total",
            "--format=csv,noheader",
        ]
    )
    return {
        "schema": "nanobot_bio_environment_manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu": gpu,
        },
        "paths": {key: str(value) for key, value in paths.items()},
        "environments": {
            "agent": _python_probe(Path(sys.executable), ("numpy", "pytest")),
            "rhobind": _python_probe(
                env_root / "rhobind" / "bin" / "python",
                ("torch", "transformers", "numpy"),
            ),
            "protein_embed": _python_probe(
                env_root / "protein_embed" / "bin" / "python",
                ("torch", "transformers", "esm"),
            ),
            "rna": _python_probe(env_root / "rna" / "bin" / "python", ("numpy",)),
            "af3_blackwell": _python_probe(
                env_root / "af3_blackwell" / "bin" / "python",
                ("jax", "jaxlib", "alphafold3"),
            ),
        },
        "immutable_inputs": [_sha256(path) for path in immutable],
        "indexes": {
            key: {
                "path": os.environ.get(key),
                "exists": bool(os.environ.get(key) and Path(os.environ[key]).exists()),
            }
            for key in ("EMB_BANK", "FOLDSEEK_DB", "SEQ_DB", "PEAKS_DB", "AFDB_DIR")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts" / "reports" / "json" / "environment_manifest.json",
    )
    args = parser.parse_args()
    manifest = build_manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
