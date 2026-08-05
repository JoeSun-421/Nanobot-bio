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


## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# $BIO_ROOT 下期望的兄弟目录：
#   nanobot-bio/
#   rhobind_agent_delivery/
#   rhobind_testdata_v2/   （可选；LOO 扩充）
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

勿写死试验机绝对路径；`nbio` 在本机发现 `DELIVERY_ROOT` / AF3 / conda。

## 快速开始

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"

./scripts/nbio.sh setup              # 首次：agent .venv + 科学 conda
nanobot-bio onboard               # 选择 LLM 厂商 + API key → .env
./scripts/nbio.sh start              # 日常万能一键：路径发现 → 纠偏 AF3/.env → chat
# ./scripts/nbio.sh start --dry-run
# source scripts/nbio.sh && nanobot-bio doctor
```

安装：[INSTALL.zh.md](INSTALL.zh.md) · [EN](INSTALL.md)。脚本：[`scripts/README.zh.md`](scripts/README.zh.md)。Delivery 桥：[`app/backends/delivery/README.zh.md`](app/backends/delivery/README.zh.md)。

一次性预测示例：

```bash
nanobot-bio agent --message "Does PTBP1 bind this RNA? <RNA sequence>"
# 或结构化输入：
nanobot-bio agent --query PTBP1 --rna-file path/to/rna.txt --device auto
```

## 常用命令及功能

| 命令 | 用途 |
|------|------|
| `./scripts/nbio.sh start` | 日常万能一键：路径发现 → GPU/AF3 适配 → heal `.env` → chat（`up` 别名） |
| `nanobot-bio chat` | 多轮交互；会话内 `/status`、`/help`、`/tools`、`/quit` |
| `nanobot-bio agent --message "..."` | 一次性预测（亦支持 `--query` / `--rna-file` / `--example`） |
| `nanobot-bio doctor` | 功能能力表：路径 / rhobind / ESM / RNA / AF3 / LLM（`--verbose` 看明细） |
| `source scripts/nbio.sh` | 仅可移植激活（另有 `status` / `setup` / `chat`；`scripts/setup/` 下为兼容薄包装） |
| `nanobot-bio onboard` | 写入 LLM provider / API key / model |
| `nanobot-bio accept-golden` | Own-head golden 验收（无 LLM；`own-head` 为其别名） |
| `nanobot-bio run-eval` | LOO 上限对照与模态消融评估 |
| `nanobot-bio evolve` | 离线自演进 → `config/evolved.candidate.yaml` |
| `nanobot-bio heavy-loo` | 隐藏自身 head 的 LOO：recovered AUPRC 与实例级指标 |
| `nanobot-bio expand-loo-matrix` | 扩充 agent 侧 LOO 转移矩阵副本 |
| `python -m rbp_eval.accept.transfer_calibration` | Transfer 校准报告（亦可 `bash scripts/cert/certify.sh --transfer`） |
| `nanobot-bio gate` | 代码与布局门禁：ruff + pytest + layout |

## 环境配置

| 项 | 说明 |
|----|------|
| 目录布局 | `rhobind_agent_delivery/` 与本仓库**同级**；可用 `DELIVERY_ROOT` 覆盖 |
| Agent 环境 | `.venv`，经 `./scripts/nbio.sh setup`（内部调用 `setup_all.sh`） |
| 科学 conda | delivery：`protein_embed` / `rna` / `rhobind` / `af3` |
| 路径 | `nbio` 在本机发现 `BIO_ROOT` / `AF3_BLACKWELL_ROOT` / conda；AutoDL 布局仅为候选之一 |
| 结构轴 | Skill：先 AFDB `structure_fetch`；仅 AFDB miss 时 AF3 `predict_structure`（仅序列目标必须调用） |
| LLM | `nanobot-bio onboard` → 必须显式选择厂商（无默认）；密钥在 `nanobot-bio/.env`，`~/.nanobot/config.json` 仅存 `${…_API_KEY}` 引用 |
| 设备 | `RHOBIND_DEVICE=auto\|cuda\|cpu`；`chat` / `agent` 亦支持 `--device` |
| 内存 | RhoBind / ESM 建议充足 RAM，并优先 CUDA；cgroup 内存过小易 OOM |

环境变量、Docker 与更细的安装路径见 [INSTALL.md](INSTALL.md)。

## 包目录索引

各包使用中英文 README（`README.md` / `README.zh.md`）：职责、`$BIO_ROOT` 下 Linux 用法、上下游链接。

| 路径 | 角色 | 文档 |
|------|------|------|
| [`app/`](app/) | CLI 与编排；[`cli/`](app/cli/)、[`backends/delivery/`](app/backends/delivery/) | [EN](app/README.md) · [中文](app/README.zh.md) |
| [`nanobot/`](nanobot/) | 精简运行时 + skill/tools SoT；[`agent/tools/rbp/`](nanobot/agent/tools/rbp/) | [EN](nanobot/README.md) · [中文](nanobot/README.zh.md) |
| [`rbp_eval/`](rbp_eval/) | 离线 LOO / 验收 / 自演进 | [EN](rbp_eval/README.md) · [中文](rbp_eval/README.zh.md) |
| [`docs/`](docs/) | 产品指南（自演进、LOO、AF3、记忆等） | [EN](docs/README.md) · [中文](docs/README.zh.md) |
| [`config/`](config/) | 默认与演化 YAML | [EN](config/README.md) · [中文](config/README.zh.md) |
| [`scripts/`](scripts/) | 安装 / CI / 认证 / Docker / 数据脚本 | [EN](scripts/README.md) · [中文](scripts/README.zh.md) |
| [`tests/`](tests/) | Pytest 契约 | [EN](tests/README.md) · [中文](tests/README.zh.md) |
| [`workspace/`](workspace/) | Skill 同步与 session/memory 符号链接 | [EN](workspace/README.md) · [中文](workspace/README.zh.md) |
| [`artifacts/`](artifacts/) | 运行产物规范目录（数据本身 gitignore） | [EN](artifacts/README.md) · [中文](artifacts/README.zh.md) |

## 文档

| 文档 | 内容 |
|------|------|
| [INSTALL.zh.md](INSTALL.zh.md) · [INSTALL.md](INSTALL.md) | 安装、环境变量、Docker、验收、CI |
| [ARCHITECTURE.zh.md](ARCHITECTURE.zh.md) · [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、记忆、桥接、eval/promote、发版 |
| [AGENTS.md](AGENTS.md) | Agent / CI 约束 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |
| [`docs/README.zh.md`](docs/README.zh.md) · [EN](docs/README.md) | 指南索引 |
| [`docs/product/SELF_EVOLUTION.zh.md`](docs/product/SELF_EVOLUTION.zh.md) | 自演进五步 |
| [`docs/guides/LOO_EXPAND.zh.md`](docs/guides/LOO_EXPAND.zh.md) | 扩充 agent 侧 LOO 矩阵 |
