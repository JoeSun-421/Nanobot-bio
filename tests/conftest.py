# -*- coding: utf-8 -*-
import pytest


@pytest.fixture(autouse=True)
def _reset_rbp_turn_guards():
    try:
        from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

        reset_stage_guards()
    except Exception:
        pass
    try:
        from nanobot.agent.tools.rbp.predict import PredictInteractionTool

        PredictInteractionTool.reset_turn_guards()
    except Exception:
        pass
    try:
        from nanobot.agent.tools.rbp.annotation import reset_tool_turn_guards

        reset_tool_turn_guards()
    except Exception:
        pass
    yield
    try:
        from nanobot.agent.tools.rbp.turn_guards import reset_stage_guards

        reset_stage_guards()
    except Exception:
        pass
