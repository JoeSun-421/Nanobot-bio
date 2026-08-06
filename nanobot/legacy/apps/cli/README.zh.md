# nanobot/legacy/apps/cli/

遗留 CLI Apps 适配器——目录/运行器桩已禁用。

[English](README.md) · [中文]

## 用途

统一 Apps 域 CLI 面的精简厂商桩。`CliAppManager` 始终报告无已安装 apps；辅助函数为旧 agent 循环提取 `@app` 会话元数据行。RBP 产品 CLI（`nanobot-bio` / `app.cli`）**不会**使用此包。

## 布局

| 模块 | 角色 |
|------|------|
| `service.py` | `CliAppError`、`CliAppsRuntimeConfig`、`CliAppManager`（空目录） |
| `utils.py` | `session_extra`、`runtime_lines`（模型可见注释） |
| `__init__.py` | 再导出 service 类型 |

## 入口

```python
from nanobot.legacy.apps.cli import CliAppManager, CliAppError, CliAppsRuntimeConfig
from nanobot.legacy.apps.cli.utils import session_extra, runtime_lines
```

## 代码示例

```python
from pathlib import Path
from nanobot.legacy.apps.cli import CliAppManager, CliAppsRuntimeConfig

mgr = CliAppManager(workspace=Path("."), runtime=CliAppsRuntimeConfig(run_timeout=30))
assert mgr.installed_names() == []
assert mgr.mentioned_installed_apps("@echo hello") == []
```

```python
from nanobot.legacy.apps.cli.utils import session_extra

assert session_extra({"cli_apps": [{"name": "echo"}]}) == {
 "cli_apps": [{"name": "echo"}]
}
assert session_extra({}) == {}
```

## 依赖 / 环境

- 纯 Python 桩；通过此管理器“安装 CLI apps”为空操作。
- RBP 工作流请优先使用 `nanobot/agent/tools/rbp/` 下的产品工具。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../README.zh.md`](../../README.zh.md) · [`../../../../app/cli/README.zh.md`](../../../../app/cli/README.zh.md)
