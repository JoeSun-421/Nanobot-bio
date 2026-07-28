# -*- coding utf-8 -*-
"""C6: evolved.candidate.yaml + promote-evolved link convergence."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG = ROOT / "config"
CANDIDATE = CONFIG / "evolved.candidate.yaml"
SEED = CONFIG / "evolved.candidate.yaml.example"
LIVE = CONFIG / "evolved.yaml"


def test_candidate_seed_is_tracked_and_well_formed():
    """The tracked seed lets a fresh clone bootstrap a candidate (C6)."""
    assert SEED.is_file(), "evolved.candidate.yaml.example seed must be tracked"
    from rbp_eval.evolve.promote import _load_yaml

    cfg = _load_yaml(SEED)
    assert cfg.get("candidate") is True
    assert cfg.get("evolved") is False


def test_promote_seeds_candidate_when_missing(tmp_path):
    """promote_evolved_config(seed=True) bootstraps the candidate from the seed."""
    from rbp_eval.evolve.promote import promote_evolved_config

    cand = tmp_path / "evolved.candidate.yaml"
    live = tmp_path / "evolved.yaml"
    # Candidate missing → seed=True should copy the tracked seed.
    # (require_reports=False so we don't need eval reports for this wiring test.)
    path = promote_evolved_config(
        candidate=cand, live=live, require_reports=False, seed=True
    )
    assert cand.is_file(), "seed should have been copied to the candidate path"
    assert path == live
    assert live.is_file()
    from rbp_eval.evolve.promote import _load_yaml

    promoted = _load_yaml(live)
    assert promoted.get("evolved") is True
    assert promoted.get("candidate") is False


def test_promote_without_seed_raises_when_missing(tmp_path):
    from rbp_eval.evolve.promote import promote_evolved_config

    cand = tmp_path / "evolved.candidate.yaml"
    live = tmp_path / "evolved.yaml"
    raised = False
    try:
        promote_evolved_config(candidate=cand, live=live, require_reports=False, seed=False)
    except FileNotFoundError:
        raised = True
    assert raised, "missing candidate without --seed must raise FileNotFoundError"


def test_live_evolved_yaml_is_marked_evolved():
    from rbp_eval.evolve.promote import _load_yaml

    live = _load_yaml(LIVE)
    assert live.get("evolved") is True
