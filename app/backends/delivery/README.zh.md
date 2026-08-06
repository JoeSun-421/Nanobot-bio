# app/backends/delivery/

从 agent 进程到同级 `rhobind_agent_delivery` 的只读桥。

[English](README.md) · [中文]

## 用途



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# 检出目录常见为 Nanobot-bio（GitHub）；小写 nanobot-bio 亦可。
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh
```

产品 agent 的全部科学 I/O 必须经本包。轻量工具可进程内执行；重工具以 JSON payload 走 `conda run` 子进程。mapping 相对 delivery 的 `agent/tools/registry.json` **失败即关闭**——陈旧绑定硬失败，而不是调用错误脚本。环境或二进制缺失时，本包绝不编造绑定分数。

端到端阶段流（own-head → retrieve → fuse → predict → integrate）见 [rbp-agent SKILL.md](../../../nanobot/skills/rbp-agent/SKILL.md)。transfer `p_hat` 的聚合权威仍是 delivery 的 `similarity_weighted_vote`。

## 布局

| 文件 | 角色 |
|------|------|
| `client.py` | `DeliveryToolClient`；`PURE_PYTHON_TOOLS` vs conda 映射 |
| `env.py` | `delivery_root()` / `apply_delivery_env()` / 路径解析 |
| `mapping.yaml` | App 编排：tool → script / env / timeout |
| `tool_mapping.py` | 校验 mapping 与 delivery registry；失败即关闭 |
| `registry.py` | `register_tools`、`build_all_tools`、阶段白名单 |
| `stage_tools.py` | 面向阶段的包装 |
| `examples.py` | 示例 / fixture 路径辅助 |
| `mmseqs_wrap.sh` | 工具链需要时的 mmseqs 包装 |
| `__init__.py` | 公共再导出 |

调用链：

```
nanobot RBP tool
 → DeliveryToolClient.call
 → apply_delivery_env / mapping
 → 进程内 或 conda run（protein_embed / rna / rhobind / af3…）
```

## 入口

```python
from app.backends.delivery import (
 DeliveryToolClient,
 apply_delivery_env,
 delivery_root,
 resolve_delivery_paths,
 register_tools,
)
```

## 代码示例

**解析 RBP 别名**

```python
from app.backends.delivery.client import DeliveryToolClient
from app.backends.delivery.env import apply_delivery_env, delivery_root

apply_delivery_env()
print("DELIVERY_ROOT →", delivery_root())
client = DeliveryToolClient()
result = client.call("resolve_rbp", {"alias": "PTBP1"})
# 结构化 dict（status / value 或 error）——绝不是合成 p_hat
```

**向 Nanobot registry 注册 delivery 工具**（通常由 `RBPAgent` 完成）

```python
from app.backends.delivery.registry import register_tools
from nanobot.agent.tools import ToolRegistry

reg = ToolRegistry()
names = register_tools(reg) # include_raw_delivery="all"（产品默认）
print(sorted(names)[:10])
# 收窄 MVP：include_raw_delivery="whitelist" 或环境变量 RBP_RAW_TOOLS=whitelist
```

**操作者冒烟**

```bash
python scripts/cert/smoke_delivery_tools.py
python scripts/cert/smoke_delivery_tools.py --network --af3
```

## 依赖 / 环境

| 变量 | 说明 |
|------|------|
| `DELIVERY_ROOT` | delivery 根；否则同级 `rhobind_agent_delivery` |
| `AGENT_DB` / `RBP_REGISTRY` / `RHOBIND_RELEASE` / `AF3_*` / `PEAKS_DB` | 由 `apply_delivery_env` 填充 |
| `RBP_BACKEND` | 产品路径为 `delivery` |
| `RBP_RAW_TOOLS` | `all`（默认）/ `whitelist`（窄 MVP 收窄）/ `none` |

子环境会清理 agent `.venv`，避免 torch / jax 栈混用。完整表见 [`INSTALL.md`](../../../INSTALL.md)。运维路径发现 / AF3 heal：`./scripts/nbio.sh start`（见 [`scripts/README.zh.md`](../../../scripts/README.zh.md)）；AutoDL 路径仅为候选之一。

## 设计思路

- **只读科学边界：** [`AGENTS.md`](../../../AGENTS.md) 禁止从 App 改 delivery 源码。
- **陈旧 mapping 失败即关闭：** 硬失败优于静默调错脚本。
- **诚实：** 结构 / AF3 缺失 → capability matrix caveat，而不是相似度 `0`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../README.zh.md`](../../README.zh.md) · [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §4 · [rbp-agent SKILL.md](../../../nanobot/skills/rbp-agent/SKILL.md) · [`../../../scripts/cert/README.zh.md`](../../../scripts/cert/README.zh.md)
