# nanobot/providers/openai_responses/

OpenAI Responses API 形态的转换器/解析器。

[English](README.md) · [中文]

## 用途

在 Nanobot 内部消息/工具结构与 OpenAI Responses API payload 之间转换。由 OpenAI 系 provider 在选用 Responses 模式时使用——不是独立 CLI。

## 布局

| 模块 | 角色 |
|------|------|
| `converters.py` | 请求/响应转换 |
| `parsing.py` | 解析 Responses API 流 / 对象 |
| `__init__.py` | 包导出 |

## 入口

```python
from nanobot.providers.openai_responses import converters, parsing
```

## 代码示例

```python
from nanobot.providers import openai_responses

print(openai_responses.__name__)
```

```python
from nanobot.providers.factory import make_provider
from nanobot.config import load_config

provider = make_provider(load_config())
```

## 依赖 / 环境

- 与父级 OpenAI 兼容 provider 相同的凭证。
- 不需要科学栈。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../README.zh.md`](../../README.zh.md)
