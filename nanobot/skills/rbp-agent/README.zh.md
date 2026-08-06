# nanobot/skills/rbp-agent/

产品 skill 包（SoT）：RNA–RBP 交互阶段与工具纪律。

[English](README.md) · [中文]

## 用途

始终启用的 Nanobot skill：教 agent 何时在 own-head 停止、如何处理 near-known / unseen 查询，以及 `p_hat` **只能**来自 predict / vote 工具。阶段是科学门控而非固定短名单；默认可用全部已注册 delivery 工具（`RBP_RAW_TOOLS=all`；设 `whitelist` 可收窄）。本目录为权威源；`python -m app.sync_overlay` 将其复制到运行时用的 `workspace/skills/rbp-agent/`。不要在 `plugin/` 下再造第三份副本。

## 布局

| 路径 | 角色 |
|------|------|
| `SKILL.md` | Skill front-matter + 阶段规则（权威） |
| `references/` | 额外片段（`stages.md`、`verdict.md`） |

同步目标：[`../../../workspace/skills/rbp-agent/`](../../../workspace/skills/rbp-agent/)（运行时；可能含 `DO_NOT_EDIT.md`）。

## 入口

```bash
$EDITOR nanobot/skills/rbp-agent/SKILL.md
python -m app.sync_overlay
nanobot-bio doctor
```

```python
from app.agent import skill_path, ensure_workspace_skill

print(skill_path())
print(ensure_workspace_skill())
```

产品工作区启动时由 `nanobot.agent.skills.SkillsLoader` 加载。

## 代码示例

**Front-matter（摘自 `SKILL.md`）**

```yaml
name: rbp-agent
metadata: {"nanobot":{"emoji":"🧬","always":true}}
always: true
```

**定位并确保 overlay**

```python
from pathlib import Path
from app.agent import skill_path, ensure_workspace_skill

sot = Path(skill_path())
assert sot.name == "SKILL.md"
assert "rbp-agent" in str(sot)
ws = Path(ensure_workspace_skill())
print(ws)
```

绑定阶段：[rbp-agent SKILL.md](SKILL.md)。

## 依赖 / 环境

- 静态仅为 Markdown skill + references。
- 运行时需要 Nanobot + `nanobot/agent/tools/rbp/` 工具。
- 在此编辑 SoT；将 `workspace/skills/rbp-agent/` 视为生成 overlay。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../agent/tools/rbp/README.zh.md`](../../agent/tools/rbp/README.zh.md) · [`../../../workspace/skills/README.zh.md`](../../../workspace/skills/README.zh.md)
