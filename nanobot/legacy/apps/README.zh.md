# nanobot/legacy/apps/

遗留 Nanobot「apps」协议（manifest 词汇）。不是 RBP 产品路径。

[English](README.md) · [中文]

## 用途

为设置界面管理的 agent apps 提供共享辅助：小型描述性 manifest schema（`agent-app.v1`），供旧 WebUI / 注册表使用。安装器仍在各自 adapter 中；本包只构建紧凑的 manifest 字典。产品运营应使用 `nanobot-bio` / `app.cli`，不要把 RBP 接到这些 apps 上。

## 布局

| 路径 | 角色 |
|------|------|
| `protocol.py` | `APP_PROTOCOL_SCHEMA`、`app_manifest`、`compact_dict` |
| `__init__.py` | 再导出 `APP_PROTOCOL_SCHEMA`、`app_manifest` |
| [`cli/`](cli/README.zh.md) | 已禁用的 CLI Apps 管理器桩 + 会话辅助 |

## 入口

```python
from nanobot.legacy.apps import APP_PROTOCOL_SCHEMA, app_manifest
from nanobot.legacy.apps.protocol import compact_dict
```

`nanobot-bio` 下无产品 CLI 入口。

## 代码示例

```python
from nanobot.legacy.apps import APP_PROTOCOL_SCHEMA, app_manifest

manifest = app_manifest(
    app_id="example.echo",
    display_name="Echo",
    description="Legacy protocol demo only",
    category="utility",
    source="local",
    capabilities=[{"name": "echo", "description": "Echo text"}],
    install={"kind": "noop"},
    remove={"kind": "noop"},
    trust={"level": "untrusted"},
    version="0.0.0",
)
assert manifest["schema"] == APP_PROTOCOL_SCHEMA  # "agent-app.v1"
assert manifest["id"] == "example.echo"
print(sorted(manifest.keys())[:6])
```

```python
from nanobot.legacy.apps.protocol import compact_dict

assert compact_dict({"a": 1, "b": None, "c": "", "d": False}) == {"a": 1, "d": False}
```

## 依赖 / 环境

- 纯 Python；RBP chat / eval / certify 不需要。
- 仍可能被 Nanobot 框架 / 设置测试导入。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`cli/README.zh.md`](cli/README.zh.md) · [`../../../app/cli/README.zh.md`](../../../app/cli/README.zh.md)
