# app/backends/delivery/

从 Agent 进程只读桥接到同级 `rhobind_agent_delivery`。

[English](README.md) · [中文]

## 功能

- 统一入口 `DeliveryToolClient.call(name, payload)` 调用全部 delivery 工具
- 轻工具：进程内 `run(payload)`；重工具：在对应 conda 环境中以 `--json` 子进程运行
- 对照 delivery `agent/tools/registry.json` 校验 `mapping.yaml`，过期绑定失败关闭
- 经 `apply_delivery_env()` 解析路径、AF3 解释器、USalign→Foldseek 回退、线程数等

## 实现方法

| 文件 | 角色 |
|------|------|
| `client.py` | `DeliveryToolClient`；`PURE_PYTHON_TOOLS` 与 `DEFAULT_CONDA_ENV` 映射 |
| `env.py` | `delivery_root()` / `apply_delivery_env()` / 路径解析 |
| `mapping.yaml` | App 编排清单：工具 → 脚本 / 环境 / 超时 |
| `tool_mapping.py` | 对照 registry 校验 mapping；过期绑定失败关闭 |
| `registry.py` | registry 辅助 |
| `stage_tools.py` | 阶段相关封装 |
| `examples.py` | 示例 / 夹具路径 |
| `mmseqs_wrap.sh` | 工具链需要时的 mmseqs 包装 |

调用链：

```
nanobot RBP tool
  → DeliveryToolClient.call
      → apply_delivery_env / mapping
      → 进程内 或 conda run (protein_embed / rna / rhobind / af3…)
```

子环境会 scrub agent `.venv`，避免 torch / jax 混装。缺 conda 时谨慎回退并返回结构化错误——**绝不**伪造结合分数。

## 怎么使用

产品代码不要直接调 delivery 脚本，应：

```python
from app.backends.delivery.client import DeliveryToolClient
client = DeliveryToolClient()
result = client.call("resolve_rbp", {"alias": "PTBP1"})
```

运维冒烟（仓库根）：

```bash
python scripts/cert/smoke_delivery_tools.py
python scripts/cert/smoke_delivery_tools.py --network --af3
```

关键环境变量（完整表见 [`INSTALL.md`](../../../INSTALL.md)）：

| 变量 | 说明 |
|------|------|
| `DELIVERY_ROOT` | delivery 根；未设则尝试同级 `rhobind_agent_delivery` |
| `AGENT_DB` / `RBP_REGISTRY` / `RHOBIND_RELEASE` / `AF3_*` / `PEAKS_DB` | 由 `apply_delivery_env` 填充 |
| `RBP_BACKEND` | 产品路径为 `delivery` |

## 设计思路

- **只读科学边界：** [`AGENTS.md`](../../../AGENTS.md) 禁止从 App 改 delivery 源码。
- **mapping 过期则失败关闭：** 宁可硬失败，也不静默调错脚本。
- **聚合权威：** Transfer `p_hat` 以 delivery `similarity_weighted_vote` 为准；LLM / 诊断不得覆盖。
- **诚实性：** 结构 / AF3 缺失 → capability matrix caveat，而不是相似度 `0`。

## 相关文档

[`../../README.zh.md`](../../README.zh.md) · [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §4 · [`../../../scripts/cert/README.zh.md`](../../../scripts/cert/README.zh.md)
