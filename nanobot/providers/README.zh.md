# nanobot/providers/

LLM provider 适配器与工厂。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`。

## 用途

在 `LLMProvider` 背后抽象 chat/completions（及相关）后端。产品 onboard 通过 `~/.nanobot/config.json` + `.env` 配置 OpenAI 兼容端点（如 DeepSeek）；工厂（`make_provider`）为 `Nanobot.from_config` 构建活动 provider。

## 布局

| 模块 | 角色 |
|------|------|
| `base.py` | `LLMProvider`、`LLMResponse` |
| `factory.py` | `make_provider`、快照 |
| `registry.py` | Provider 注册辅助 |
| `openai_compat_provider.py` | OpenAI 兼容（DeepSeek 等） |
| `anthropic_provider.py` / `azure_openai_provider.py` / `bedrock_provider.py` / … | 其他后端 |
| `fallback_provider.py` | 回退链 |
| `openai_codex_provider.py` / `github_copilot_provider.py` | 额外适配 |
| `image_generation.py` / `transcription.py` | 多模态辅助 |
| [`openai_responses/`](openai_responses/README.zh.md) | Responses API 转换/解析 |

## 入口

```python
from nanobot.providers import LLMProvider, LLMResponse, OpenAICompatProvider
from nanobot.providers.factory import make_provider
from nanobot.config import load_config
```

## 代码示例

```python
from nanobot.config import load_config
from nanobot.providers.factory import make_provider

cfg = load_config()
provider = make_provider(cfg)
print(type(provider).__name__)
```

```bash
nanobot-bio onboard --provider openai --model deepseek-chat
nanobot-bio doctor
```

## 依赖 / 环境

- API key 经配置引用的环境变量——切勿硬编码。
- 构建 provider 本身不需要 delivery/GPU。

## 相关文档

[`openai_responses/README.zh.md`](openai_responses/README.zh.md) · [`../config/README.zh.md`](../config/README.zh.md) · [`../../app/core/README.zh.md`](../../app/core/README.zh.md)
