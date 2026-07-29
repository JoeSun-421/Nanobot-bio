<div align="center">
  <img src="assets/nanobot_logo.png" alt="nanobot-bio" width="420">

  <h1>Nanobot-bio</h1>
  <p>RNA–RBP 相互作用预测 Agent</p>

  <p>
    <a href="https://github.com/JoeSun-421/rbp-nanobot-bio/stargazers"><img src="https://img.shields.io/github/stars/JoeSun-421/rbp-nanobot-bio?style=flat" alt="Stars"></a>
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/Nanobot-HKUDS%2Fnanobot-111111?logo=github" alt="Nanobot"></a>
    <img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue" alt="Python ≥3.10">
    <img src="https://img.shields.io/badge/version-0.5.1-green" alt="Version">
    <a href="https://github.com/JoeSun-421/rbp-nanobot-bio/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/JoeSun-421/rbp-nanobot-bio/ci.yml?branch=main&label=CI" alt="CI"></a>
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

将 `rhobind_agent_delivery/` 与本仓库放在同一父目录下（目前未放入本仓库）：

```bash
cd nanobot-bio
bash scripts/setup_all.sh
source .venv/bin/activate

nanobot-bio onboard    # 选择 LLM 厂商 + API key → .env（config 仅 ${VAR} 引用）
nanobot-bio doctor     # 路径 / conda / 科学栈自检
nanobot-bio chat
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
| `nanobot-bio doctor` | delivery 路径、科学环境、`PEAKS_DB`、AF3、LLM 配置自检 |
| `nanobot-bio onboard` | 写入 LLM provider / API key / model |
| `nanobot-bio accept-golden` | Own-head golden 验收（无 LLM；`own-head` 为其别名） |
| `nanobot-bio run-eval` | LOO 上限对照与模态消融评估 |
| `nanobot-bio heavy-loo` | 隐藏自身 head 的 LOO：recovered AUPRC 与实例级指标 |
| `python -m rbp_eval.accept.transfer_calibration` | Transfer 校准报告（亦可 `bash scripts/certify.sh --transfer`） |
| `nanobot-bio gate` | 代码与布局门禁：ruff + pytest + layout |

## 环境配置

| 项 | 说明 |
|----|------|
| 目录布局 | `rhobind_agent_delivery/` 与本仓库**同级**；可用 `DELIVERY_ROOT` 覆盖 |
| Agent 环境 | `nanobot-bio/.venv`（由 `setup_all.sh` 创建） |
| 科学 conda | delivery：`protein_embed` / `rna` / `rhobind` / `af3` |
| LLM | `nanobot-bio onboard` → 必须显式选择厂商（无默认）；密钥在 `nanobot-bio/.env`，`~/.nanobot/config.json` 仅存 `${…_API_KEY}` 引用 |
| 设备 | `RHOBIND_DEVICE=auto\|cuda\|cpu`；`chat` / `agent` 亦支持 `--device` |
| 内存 | RhoBind / ESM 建议充足 RAM，并优先 CUDA；cgroup 内存过小易 OOM |

环境变量、Docker 与更细的安装路径见 [INSTALL.md](INSTALL.md)。
