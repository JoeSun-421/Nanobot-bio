# nanobot/command/

Nanobot CLI/chat 面的斜杠命令路由与内置处理器。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 用途

通过 `CommandRouter` 将会话内斜杠命令（`/…`）路由到处理器，并由 `register_builtin_commands` 注册内置命令。产品 CLI（`nanobot-bio …`）是另一套（`app.cli`）；本包是框架的会话内命令层。

## 布局

| 模块 | 角色 |
|------|------|
| `router.py` | `CommandRouter`、`CommandContext` |
| `builtin.py` | `register_builtin_commands` |
| `__init__.py` | 再导出 |

## 入口

```python
from nanobot.command import CommandRouter, CommandContext, register_builtin_commands
```

## 代码示例

```python
from nanobot.command.router import CommandRouter, CommandContext

router = CommandRouter()
# 框架 chat loop 启动时通过 register_builtin_commands(router) 注册处理器
print(CommandRouter, CommandContext)
```

## 依赖 / 环境

- 仅框架。产品科学命令在 `app.cli` / `rbp_eval`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../app/cli/README.zh.md`](../../app/cli/README.zh.md)
