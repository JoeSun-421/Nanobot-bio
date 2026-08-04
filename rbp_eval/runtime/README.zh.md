# rbp_eval/runtime/

评估 / 自进化 trace 钩子与结构化 JSONL 事件 schema。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`。

## 用途

提供稳定的 trace 事件，供离线 evolve 做工具归因与代理缓存提升。`JsonlTraceHook` 无需 Nanobot（CI / 离线）。安装 Nanobot 时，`nanobot_hooks.RBPTraceHook` 继承真实 `AgentHook`，记录工具执行前后。所有行应通过 `trace_schema.make_event` 构建（`schema: rbp_trace/v1`）。

## 布局

| 模块 | 角色 |
|------|------|
| `trace_schema.py` | `make_event`、`validate_event`、规范 `EVENT_TYPES` |
| `hooks.py` | 离线 `JsonlTraceHook`（兼用旧名 `RBPTraceHook`） |
| `nanobot_hooks.py` | 可用 nanobot 时的真实 `AgentHook` 实现 |
| `__init__.py` | 包标记 |

## 入口

```python
from rbp_eval.runtime.trace_schema import make_event, validate_event, EVENT_TYPES
from rbp_eval.runtime.hooks import JsonlTraceHook
# 安装 nanobot 后：
# from rbp_eval.runtime.nanobot_hooks import RBPTraceHook
```

无独立 CLI——由评估 runner / agent 集成挂载钩子。

## 代码示例

**构建并校验 trace 行**

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

**离线 JSONL 记录器**

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

## 依赖 / 环境

- `hooks.JsonlTraceHook`：仅需标准库（+ 可选 `trace_schema`）。
- `nanobot_hooks.RBPTraceHook`：需要 `nanobot` agent hook 基类。
- 默认评估 trace 路径来自 `app.core.paths` / evolve runner（`--trace`）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../evolve/README.zh.md`](../evolve/README.zh.md) · [`../../artifacts/README.zh.md`](../../artifacts/README.zh.md)
