# nanobot/agent/tools/rbp/

产品 RBP 工具包（SoT）。Tool 子类经 delivery 取分；LLM 只做编排。

[English](README.md) · [中文]

## 用途

这些工具实现 [`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../../docs/product/BINDING_PREDICTION_FLOW.zh.md) 中的科学阶段：catalogue 解析 / own-head 预测、多视图检索、融合、结构、注释与 evolve 辅助。数值（`prob`、相似度、序列、引用）**只**来自工具返回——绝不来自模型记忆。注册经 `ALL_RBP_TOOL_CLASSES` + 可选 `RBP_PHMMER` 精选挂载。

## 布局

| 模块 | 工具 / 角色 |
|------|-------------|
| `predict.py` | `PredictInteractionTool` — own-head / donor-head 预测 |
| `seq.py` | `SeqSimilarityTool` — 序列相似检索 |
| `structure.py` | `PredictStructureTool`、`StructSimilarityTool` |
| `annotation.py` | `GetFuncAnnotationTool`、`LiteratureSearchTool` |
| `catalogue.py` | `GetKnownRBPListTool` |
| `near_known.py` | `CheckNearKnownTool` |
| `phmmer.py` | `PhmmerSimilarityTool`（可选；`RBP_PHMMER=1`） |
| `evolve_tools.py` | `FuseSimilarityViewsTool`、`LookupProxyCacheTool` |
| `commit_proxies.py` | `CommitProxyCandidatesTool` |
| `common.py` | 共享辅助 / 返回信封 |
| `stage_contract.py` | 阶段契约 / 守卫 |
| `turn_guards.py` | 回合级安全守卫 |
| `register.py` | `app.agent` 使用的 `register_rbp_tools()` |
| `__init__.py` | `register_all()`、`ALL_RBP_TOOL_CLASSES` |

## 入口

```python
from nanobot.agent.tools.rbp import (
    register_all,
    ALL_RBP_TOOL_CLASSES,
    PredictInteractionTool,
)
from nanobot.agent.tools.rbp.register import register_rbp_tools
```

## 代码示例

**挂载默认产品集合**

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp import register_all

reg = ToolRegistry()
print(register_all(reg))
```

**App 路径（默认挂载全量 delivery 工具面）**

```python
from nanobot.agent.tools import ToolRegistry
from nanobot.agent.tools.rbp.register import register_rbp_tools

reg = ToolRegistry()
_, names = register_rbp_tools(reg)  # 默认 include_raw_delivery="all"
print(len(names), "tools mounted")
# 窄 MVP：include_raw_delivery="whitelist" 或 RBP_RAW_TOOLS=whitelist
```

**改完本包后**

```bash
python -m app.sync_overlay
nanobot-bio doctor
pytest tests/test_proposal_compliance.py
```

## 依赖 / 环境

- 运行时经 `app.backends.delivery.DeliveryToolClient`（需要 `DELIVERY_ROOT` + conda 映射）。
- `RBP_RAW_TOOLS=all|whitelist|none` 控制 raw delivery 工具挂载（默认 **`all`**；设 `whitelist` 可收窄）。
- `RBP_PHMMER=1` 增加 `PhmmerSimilarityTool`（需要 hmmer）。

## 设计思路

- 失败即关闭：OOM / 超时 / null prob → 结构化错误 / null `p_hat`，不编造重试分数。
- Transfer 聚合权威留在 delivery `similarity_weighted_vote`。
- Skill（`nanobot/skills/rbp-agent`）编码 Stage 0 STOP；工具强制返回信封。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../../skills/README.zh.md`](../../../skills/README.zh.md) · [`../../../../app/backends/delivery/README.zh.md`](../../../../app/backends/delivery/README.zh.md) · [`../../../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
