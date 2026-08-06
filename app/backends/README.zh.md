# app/backends/

科学 I/O 后端适配层。产品路径只使用 **delivery** 后端。

[English](README.md) · [中文]

## 用途

本包是 App 与外部科学栈对话的命名空间。当前唯一生产后端是 [`delivery/`](delivery/README.zh.md)：只读桥接到同级 `rhobind_agent_delivery`。历史 mock 后端不再作为可导入产品代码提供——支持的设置是 `RBP_BACKEND=delivery`。

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 布局

| 路径 | 角色 |
|------|------|
| `__init__.py` | 包标记（`Backends: mock vs delivery`） |
| [`delivery/`](delivery/README.zh.md) | `DeliveryToolClient`、环境解析、`mapping.yaml`、registry |

## 入口

```python
from app.backends.delivery import DeliveryToolClient, apply_delivery_env, delivery_root

apply_delivery_env()
client = DeliveryToolClient()
print(delivery_root())
```

请从 `app.backends.delivery`（或其子模块）导入，不要直接调用 delivery 脚本。

## 代码示例

```python
from app.backends.delivery.client import DeliveryToolClient
from app.backends.delivery.env import apply_delivery_env, resolve_delivery_paths

apply_delivery_env()
paths = resolve_delivery_paths()
client = DeliveryToolClient()
# 轻量工具（mapping 为 pure Python 时进程内执行）：
result = client.call("resolve_rbp", {"alias": "PTBP1"})
```

仓库根冒烟：

```bash
python scripts/cert/smoke_delivery_tools.py
```

## 依赖 / 环境

| 变量 | 说明 |
|------|------|
| `DELIVERY_ROOT` | 覆盖路径；否则同级 `../rhobind_agent_delivery` |
| `RBP_BACKEND` | 产品路径：`delivery` |
| 科学 conda 环境 | 重工具经 `conda run`（见 delivery `mapping.yaml`） |

## 相关文档

[`delivery/README.zh.md`](delivery/README.zh.md) · [`../README.zh.md`](../README.zh.md) · [rbp-agent SKILL.md](../../nanobot/skills/rbp-agent/SKILL.md) · [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §4
