<div align="center">
  <img src="assets/nanobot_logo.png" alt="nanobot-bio" width="420">

  <h1>Nanobot-bio</h1>
  <p>RNA–RBP 相互作用预测 Agent</p>

  <p>
    <a href="https://github.com/JoeSun-421/Nanobot-bio/stargazers"><img src="https://img.shields.io/github/stars/JoeSun-421/Nanobot-bio?style=flat" alt="Stars"></a>
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/Nanobot-HKUDS%2Fnanobot-111111?logo=github" alt="Nanobot"></a>
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue" alt="Python ≥3.10">
    <img src="https://img.shields.io/badge/version-0.5.1-green" alt="Version">
    <a href="https://github.com/JoeSun-421/Nanobot-bio/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/JoeSun-421/Nanobot-bio/ci.yml?branch=main&label=CI" alt="CI"></a>
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>

  <p><a href="README.md">English</a> · <b>中文</b></p>
</div>

## 项目介绍

**nanobot-bio** 是面向 RNA–蛋白结合预测的命令行科学 Agent，基于 [Nanobot](https://github.com/HKUDS/nanobot)开发，并通过同级 `rhobind_agent_delivery` 工具桥接 RhoBind 与多模态检索栈。给定 RBP 身份与 RNA 序列，系统输出类型约束的 JSON 结论：`label`、`confidence`、`p_hat`、`explanation`、`supporting_rbps`。

两种工作模式：

- **Own-head：** 目标 RBP 在 catalogue / panel 中且已有 RhoBind head → 直接对该 head 打分并给出结论。
- **Transfer：** 目标在 panel 外或未见 → 多模态检索供体 RBP，再经加权投票（`similarity_weighted_vote`）聚合供体预测。


预测流程概览：

| 阶段 | 作用 |
|------|------|
| **0** | 解析 RBP 身份；若 in-panel → own-head 预测并结束 |
| **1** | 多视图检索 → 融合相似度 → 选定供体（必要时弃权） |
| **2** | 对供体批量 `predict_interaction`，默认加权聚合 |
| **3** | 证据核对与可选先验 → 写出 verdict |


## 快速开始

```bash
git clone https://github.com/JoeSun-421/Nanobot-bio.git
cd Nanobot-bio
# 将 rhobind_agent_delivery/ 放在与本仓同级的父目录下（delivery 不在本 git 仓内）：
#   parent/Nanobot-bio
#   parent/rhobind_agent_delivery

./scripts/nbio setup              # 首次：agent .venv + 科学 conda
source scripts/nbio               # 日常：激活并导出路径（只探测，不重装）
nanobot-bio onboard               # 选择 LLM 厂商 + API key → .env
nanobot-bio doctor                # 功能能力表（异常行优先）
nanobot-bio chat
# 或: ./scripts/nbio chat
```

逐步安装与路径说明见 [INSTALL.md](INSTALL.md)。

一次性预测示例：

```bash
nanobot-bio agent --message "Does PTBP1 bind this RNA? <RNA sequence>"
# 或结构化输入：
nanobot-bio agent --query PTBP1 --rna-file path/to/rna.txt --device auto
```

## 常用命令及功能

| 命令 | 用途 |
|------|------|
| `nanobot-bio chat` | 多轮交互；会话内 `/status`、`/help`、`/tools`、`/quit` |
| `nanobot-bio agent --message "..."` | 一次性预测（亦支持 `--query` / `--rna-file` / `--example`） |
| `nanobot-bio doctor` | 功能能力表：路径 / rhobind / ESM / RNA / AF3 / LLM（`--verbose` 看明细） |
| `source scripts/nbio` | 可移植日常激活（另有 `status` / `setup` / `chat`） |
| `nanobot-bio onboard` | 写入 LLM provider / API key / model |
| `nanobot-bio accept-golden` | Own-head golden 验收（无 LLM；`own-head` 为其别名） |
| `nanobot-bio run-eval` | LOO 上限对照与模态消融评估 |
| `nanobot-bio heavy-loo` | 隐藏自身 head 的 LOO：recovered AUPRC 与实例级指标 |
| `python -m rbp_eval.accept.transfer_calibration` | Transfer 校准报告（亦可 `bash scripts/cert/certify.sh --transfer`） |
| `nanobot-bio gate` | 代码与布局门禁：ruff + pytest + layout |

## 环境配置

| 项 | 说明 |
|----|------|
| 目录布局 | `rhobind_agent_delivery/` 与本仓库**同级**；可用 `DELIVERY_ROOT` 覆盖 |
| Agent 环境 | `.venv`，经 `./scripts/nbio setup`（内部调用 `setup_all.sh`） |
| 科学 conda | delivery：`protein_embed` / `rna` / `rhobind` / `af3` |
| LLM | `nanobot-bio onboard` → 必须显式选择厂商（无默认）；密钥在 `nanobot-bio/.env`，`~/.nanobot/config.json` 仅存 `${…_API_KEY}` 引用 |
| 设备 | `RHOBIND_DEVICE=auto\|cuda\|cpu`；`chat` / `agent` 亦支持 `--device` |
| 内存 | RhoBind / ESM 建议充足 RAM，并优先 CUDA；cgroup 内存过小易 OOM |

环境变量、Docker 与更细的安装路径见 [INSTALL.md](INSTALL.md)。

## 包目录索引

各包使用**分开的**中英文 README（`README.md` / `README.zh.md`），内容覆盖功能、实现方法、怎么使用、设计思路。

| 路径 | 角色 | 文档 |
|------|------|------|
| [`app/`](app/) | CLI 与编排；[`cli/`](app/cli/)、[`backends/delivery/`](app/backends/delivery/) | [EN](app/README.md) · [中文](app/README.zh.md) |
| [`nanobot/`](nanobot/) | 精简运行时 + skill/tools SoT；[`agent/`](nanobot/agent/)、[`sdk/`](nanobot/sdk/) | [EN](nanobot/README.md) · [中文](nanobot/README.zh.md) |
| [`rbp_eval/`](rbp_eval/) | 离线 LOO / 验收 / 自演化 | [EN](rbp_eval/README.md) · [中文](rbp_eval/README.zh.md) |
| [`config/`](config/) | 默认与演化 YAML | [EN](config/README.md) · [中文](config/README.zh.md) |
| [`scripts/`](scripts/) | 安装 / CI / 认证 / Docker / 数据脚本 | [EN](scripts/README.md) · [中文](scripts/README.zh.md) |
| [`tests/`](tests/) | Pytest 契约 | [EN](tests/README.md) · [中文](tests/README.zh.md) |
| [`workspace/`](workspace/) | Skill 同步与 session/memory 符号链接 | [EN](workspace/README.md) · [中文](workspace/README.zh.md) |
| [`artifacts/`](artifacts/) | 运行产物规范目录（数据本身 gitignore） | [EN](artifacts/README.md) · [中文](artifacts/README.zh.md) |

## 文档

| 文档 | 内容 |
|------|------|
| [INSTALL.md](INSTALL.md) | 安装、环境变量、Docker、验收、CI runner |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、记忆、桥接、eval/promote、slim vendor、发版 |
| [AGENTS.md](AGENTS.md) | Agent / CI 约束 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |
