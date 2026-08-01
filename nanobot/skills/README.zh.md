# nanobot/skills/

Skill 真相源目录（Markdown skill 包）。**不是** Python 包。

[English](README.md) · [中文]

## 用途

Skills 教 agent *何时*、*如何* 调用工具。nanobot-bio 的产品 skill 是 `rbp-agent`：Stage 0 own-head 快路径、near-known 处理、unseen 的 retrieve→fuse→predict→integrate，以及 `p_hat` 只能来自 predict 工具的规则。本树为 SoT；`python -m app.sync_overlay` 将其同步到 `workspace/skills/` 供运行时使用。

## 布局

| 路径 | 角色 |
|------|------|
| [`rbp-agent/`](rbp-agent/README.zh.md) · `SKILL.md` | 产品 skill（always-on） |
| `rbp-agent/references/` | skill 额外参考片段 |

同步目标：`workspace/skills/rbp-agent/`（见 [`../../workspace/README.zh.md`](../../workspace/README.zh.md)）。

## 入口

由 `nanobot.agent.skills.SkillsLoader` 在 Nanobot 以产品 workspace 启动时加载。操作者在此编辑 SoT（或依赖 overlay 同步）。

```bash
$EDITOR nanobot/skills/rbp-agent/SKILL.md
python -m app.sync_overlay
nanobot-bio doctor
```

## 代码示例

**从产品辅助定位 skill**

```python
from app.agent import skill_path, ensure_workspace_skill

print(skill_path())
print(ensure_workspace_skill())
```

**Skill front-matter（摘录）**

```yaml
name: rbp-agent
metadata: {"nanobot":{"emoji":"🧬","always":true}}
always: true
```

绑定阶段：[`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)。

## 依赖 / 环境

- 静态为 Markdown；运行时需要 Nanobot + 已挂载的 RBP tools。
- 不要在 `plugin/` 下再复制第三份 tools —— SoT 是本树 + `agent/tools/rbp/`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../agent/tools/rbp/README.zh.md`](../agent/tools/rbp/README.zh.md) · [`../../workspace/skills/README.zh.md`](../../workspace/skills/README.zh.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md)
