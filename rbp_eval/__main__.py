# -*- coding: utf-8 -*-
"""Allow ``python -m rbp_eval`` help."""

from __future__ import annotations


def main() -> int:
    print(
        "rbp_eval modules (evaluation package):\n"
        "  python -m rbp_eval.loo.loo_eval [--out artifacts/reports/json/eval_loo_report.json]\n"
        "  python -m rbp_eval.evolve.runner [--evolve]\n"
        "  python -m rbp_eval.plans.evaluation_plan [--with-seq] [--labels PATH]\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
