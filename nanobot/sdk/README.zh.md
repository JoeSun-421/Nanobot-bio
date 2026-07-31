# nanobot/sdk/

支撑高阶 Nanobot Python API 的内部辅助模块。

[English](README.md) · [中文]

## 功能

- 支撑 `nanobot.nanobot.Nanobot` 的内部实现（流式事件、客户端、运行时类型）
- **不是**给产品协作方用的第二套公共 API

## 实现方法

| 文件 | 角色 |
|------|------|
| `clients.py` | SDK 客户端辅助 |
| `runtime.py` | 运行时胶水 |
| `streaming.py` | 流式事件相关 |
| `types.py` | 共享类型 |
| `__init__.py` | 包说明（internal helpers） |

关系：

```
nanobot/nanobot.py  (公共 API)
    └── nanobot/sdk/*  (内部细节)
app/agent.py        (产品组装 → Nanobot)
```

## 怎么使用

优先用产品 CLI 或高阶导入：

```bash
nanobot-bio chat|agent
```

```python
from nanobot import Nanobot  # 或 Nanobot.from_config
```

不要把 `nanobot.sdk.*` 当成对外稳定契约。

## 设计思路

- 公共面保持小（`Nanobot` + CLI），内部可重构 streaming/client 细节。
- LLM 凭证仍走 onboard / `.env` / `~/.nanobot/config.json`，不在此硬编码。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../app/README.zh.md`](../../app/README.zh.md)
