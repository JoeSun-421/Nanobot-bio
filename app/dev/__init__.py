# -*- coding: utf-8 -*-
"""Dev package — engineering gates (C5 boundary).

This package holds the **engineering** maturity gates only:

* ``gate``  — pytest / ruff / layout + optional light eval (CI gate)
* ``compliance`` — SoT compliance checks
* ``layout`` — SoT layout verification
* ``mvp`` — Agent-Owner MVP acceptance (levels A–F; engineering structure)

The **scientific** ``accept-*`` commands live in :mod:`rbp_eval`
(``accept_llm``, ``own_head``/``accept-golden``) — do not add scientific
acceptance paths here. This separation keeps engineering gates (fast, no
delivery/GPU) distinct from scientific acceptance (needs delivery + envs).
"""

from __future__ import annotations
