# nanobot/config/

Nanobot 配置加载、路径与 schema（`Config`）。

[English](README.md) · [中文]

## 用途

加载 `~/.nanobot/config.json`（或覆盖路径），解析 `${ENV}` 占位符，并暴露类型化 `Config` 与路径辅助。产品科学旋钮（融合权重、阈值）在仓库 `config/*.yaml`，经 `app.core.runtime_config`——本包是**框架**侧 LLM/workspace 配置。

## 布局

| 模块 | 角色 |
|------|------|
| `loader.py` | `load_config`、`save_config`、`resolve_config_env_vars`、`get_config_path` |
| `schema.py` | `Config` 树 |
| `paths.py` | data / workspace / cron / logs 路径辅助 |
| `__init__.py` | 再导出 |

## 入口

```python
from nanobot.config import load_config, get_config_path, Config, get_workspace_path
```

## 代码示例

```python
from nanobot.config import load_config, get_config_path, get_workspace_path

print(get_config_path())
cfg = load_config()
print(get_workspace_path(cfg))
```

```bash
nanobot-bio onboard
```

## 依赖 / 环境

- 配置可引用 `${DEEPSEEK_API_KEY}` 等——密钥勿进 git。
- 产品 YAML：[`../../config/README.zh.md`](../../config/README.zh.md)。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../app/core/README.zh.md`](../../app/core/README.zh.md) · [`INSTALL.md`](../../INSTALL.md)
