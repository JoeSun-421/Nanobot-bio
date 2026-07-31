# workspace/skills/

从仓内 SoT 同步出来的运行时 skill 副本。

[English](README.md) · [中文]

## 功能

- Nanobot 运行时加载的 skill 目录
- 当前产品 skill：`rbp-agent/`
- 由 SoT 同步；同步后可能出现 `DO_NOT_EDIT.md` 提示

## 实现方法

| 位置 | 角色 |
|------|------|
| **SoT（请编辑这里）** | `nanobot/skills/rbp-agent/SKILL.md` |
| **运行副本** | `workspace/skills/rbp-agent/`（`sync_overlay` 生成） |

`rbp-agent` 要点（完整阶段纪律见 SoT）：

- 阶段 0：catalogue 内 RBP → `resolve_rbp` + 一次 `predict_interaction`（own-head），写出 JSON 结论后停止
- 未见 RBP：retrieve → donor predict → integrate；`p_hat` 只来自 predict / vote 工具
- 两个 LLM 检查点（检索推理 / 解释）；不得编造分数

## 怎么使用

```bash
python -m app.sync_overlay
# 或
nanobot-bio doctor
```

然后跑 `nanobot-bio chat` / `agent`。写作请打开 `nanobot/skills/` 下的 SoT，而不只改本副本。

## 设计思路

- 运行时工作区需要 skill 路径；SoT 放在 `nanobot/` 保持 slim-vendor「SoT == 运行时」，同时同步出 workspace 可见树。
- 只改 workspace 副本会在下次 sync 丢失。
- Skill 不得指示模型编造概率或跳过 delivery 投票（[`AGENTS.md`](../../AGENTS.md)）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../nanobot/README.zh.md`](../../nanobot/README.zh.md) · [`AGENTS.md`](../../AGENTS.md)
