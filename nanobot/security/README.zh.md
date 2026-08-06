# nanobot/security/

工作区访问策略与网络安全辅助。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 用途

约束工具/channel 在 workspace 下可读写的范围，并提供网络 / SSRF 相关防护。在启用遗留文件系统/web 工具时尤其重要；产品 RBP 模式仍受益于默认 workspace 策略。

## 布局

| 模块 | 角色 |
|------|------|
| `workspace_access.py` | Scope / sandbox 状态、`ToolWorkspace`、访问模式 |
| `workspace_policy.py` | `resolve_path`、`is_path_allowed`、`require_path_within` |
| `network.py` | `validate_url_target`、SSRF 白名单辅助 |

## 入口

```python
from nanobot.security.workspace_policy import resolve_path, is_path_within, require_path_within
from nanobot.security.network import validate_url_target, configure_ssrf_whitelist
from nanobot.security.workspace_access import default_workspace_scope, workspace_sandbox_status
```

`__init__.py` 有意保持精简——请从上述模块导入。

## 代码示例

```python
from pathlib import Path
from nanobot.security.workspace_policy import is_path_within, resolve_path

ws = Path("workspace").resolve()
target = resolve_path("notes.md", workspace=ws)
assert is_path_within(target, ws)

from nanobot.security.network import validate_url_target
ok, reason = validate_url_target("https://example.com/api")
print(ok, reason)
```

```bash
nanobot-bio layout
```

## 依赖 / 环境

- `load_config` 期间可能应用配置驱动白名单（见 `nanobot.config.loader`）。
- 不依赖科学 conda。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../config/README.zh.md`](../config/README.zh.md)
