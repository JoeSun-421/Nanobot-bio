# rbp_eval/runtime/

Eval / self-evolution trace hooks and structured JSONL event schema.

[English] · [中文](README.zh.md)

> Parent package map and `$BIO_ROOT` layout: [`README.md`](../../README.md). Activate with `cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`.

## Purpose

Provides stable trace events so offline evolve can attribute tools and promote proxy caches. `JsonlTraceHook` works without Nanobot (CI / offline). When Nanobot is installed, `nanobot_hooks.RBPTraceHook` subclasses the real `AgentHook` and records before/after tool execution. All rows should be buildable via `trace_schema.make_event` (`schema: rbp_trace/v1`).

## Layout

| Module | Role |
|--------|------|
| `trace_schema.py` | `make_event`, `validate_event`, canonical `EVENT_TYPES` |
| `hooks.py` | Offline `JsonlTraceHook` (also exported as legacy name `RBPTraceHook`) |
| `nanobot_hooks.py` | Real `AgentHook` implementation when nanobot is available |
| `__init__.py` | Package marker |

## Entry points

```python
from rbp_eval.runtime.trace_schema import make_event, validate_event, EVENT_TYPES
from rbp_eval.runtime.hooks import JsonlTraceHook
# When nanobot installed:
# from rbp_eval.runtime.nanobot_hooks import RBPTraceHook
```

No dedicated CLI — hooks are attached by eval runners / agent integration.

## Code examples

**Build and validate a trace row**

```python
from rbp_eval.runtime.trace_schema import make_event, validate_event

row = make_event(
    "tool_result",
    session_key="rbp:eval",
    tool="resolve_rbp",
    status="ok",
    latency_ms=12.5,
    alias="PTBP1",
)
assert row["schema"] == "rbp_trace/v1"
assert validate_event(row) == []
print(row["type"], row["tool"])
```

**Offline JSONL logger**

```python
from pathlib import Path
from rbp_eval.runtime.hooks import JsonlTraceHook

hook = JsonlTraceHook(Path("artifacts/traces/demo.jsonl"), session_key="rbp:demo")
hook.on_query_end(
    "Does PTBP1 bind this RNA?",
    {"verdict": {"p_hat": 0.9, "label": "Strong"}},
    tool_calls=[{"tool": "resolve_rbp"}],
)
print(hook.out_path.read_text(encoding="utf-8").splitlines()[-1][:120])
```

## Dependencies / env

- `hooks.JsonlTraceHook`: stdlib only (+ optional `trace_schema`).
- `nanobot_hooks.RBPTraceHook`: requires `nanobot` agent hook base class.
- Default eval trace paths come from `app.core.paths` / evolve runner (`--trace`).

## See also

[`../README.md`](../README.md) · [`../evolve/README.md`](../evolve/README.md) · [`../../artifacts/README.md`](../../artifacts/README.md)
