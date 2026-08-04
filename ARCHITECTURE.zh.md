# 架构说明

<p><a href="ARCHITECTURE.md">English</a> · <b>中文</b></p>

`nanobot-bio` 工程地图：分层、工作区存储、eval/promote、slim-vendor 与发版清单。  
安装：[INSTALL.zh.md](INSTALL.zh.md) / [INSTALL.md](INSTALL.md)。Agent 门禁：[AGENTS.md](AGENTS.md)。历史：[CHANGELOG.md](CHANGELOG.md)。  
各包 README 对：见根 [README.zh.md](README.zh.md) 包地图。本地提案细节在 gitignore 的 `docs/`。

## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
# DELIVERY_ROOT=$BIO_ROOT/rhobind_agent_delivery
```

---

## 1. 分层

| 层 | 路径 | 角色 |
|----|------|------|
| Agent CLI + core | `app/` | argparse CLI、verdict schema、runtime config、onboard、delivery 桥。**从不自算 `p_hat`** |
| Runtime + skill（SoT） | `nanobot/` | 仓内精简 Nanobot + `rbp-agent` skill / RBP 工具。SoT == runtime |
| 离线 eval + evolve | `rbp_eval/` | LOO、融合、验收、自演进 |
| 科学包（只读） | `$BIO_ROOT/rhobind_agent_delivery/` | 经 App 桥调用；勿改 |

`NANOBOT_SRC` 默认真仓内 `nanobot/`。无兄弟 clone 运行时。

| 区域 | 路径 |
|------|------|
| 循环 / 记忆 / 上下文 | `nanobot/agent/` |
| 工具运行时 | `nanobot/agent/tools/core/` |
| 产品工具箱 | `nanobot/agent/tools/rbp/` |
| 会话 | `nanobot/session/` |
| Skill SoT | `nanobot/skills/rbp-agent/` |

**ToolLoader：** 默认 `NANOBOT_TOOL_ALLOW=rbp`。  
**Eval 包：** `rbp_eval/{scoring,loo,evolve,accept,runtime,rna,plans}/` — 物理路径 = import 路径。

---

## 2. 工作区：会话 vs 长期记忆

**可写真相源是 `artifacts/`**（`workspace/sessions` 与 `workspace/memory` 仅为符号链接）。详情：[docs/guides/MEMORY_AND_SESSIONS.zh.md](docs/guides/MEMORY_AND_SESSIONS.zh.md)。

| 存储 | 路径 | 用途 |
|------|------|------|
| 会话转录 | `artifacts/sessions/` | 按会话 key / 日期的聊天 JSONL |
| PA 长期记忆 | `artifacts/memory/` | `MEMORY.md`、Dream 游标；scientific_mode **关闭** |
| 领域记忆 | `artifacts/cache/proxy_map.json` | 检索捷径；不改 RhoBind 分数 |
| Eval 报告 | `artifacts/reports/{json,md,csv}/` | JSON / Markdown / CSV |
| Skill 链接 | `workspace/skills/rbp-agent/` | 须跟踪仓内 SoT（`python -m app.sync_overlay`） |

科学模式不注入 `USER.md` / `MEMORY.md`。`accept-llm` / `chat` / `agent` 默认 `ephemeral=True`。实现：`nanobot/session/manager.py`、`nanobot/agent/memory.py`。

---

## 3. 预测流水线

问题：*这段 RNA 是否结合 RBP X？* — X 可能没有训练 head。

1. **Retrieve** catalogue 邻域（seq / struct / func）→ donors  
2. **Predict** 在每个 donor head 上对查询 RNA 打分 → `prob`  
3. **Integrate** → 可校准、可解释的 verdict  

两处 LLM 检查点：Stage-1（检索/供体）与 Stage-3（解释）。LLM **不得**编造 `p_hat`、motif 或注释。

- Own-head：`p_hat = max_windows fθ(RNA, head_target)`  
- Transfer：经 delivery `similarity_weighted_vote`；`sᵢ` 来自 `rbp_eval/scoring/fuse_hits.py`  
- RNA peak-homology 融合权重保持 `0`，除非 peaks DB 就绪。诚实 SoT：`app/core/capability_matrix.py`

---

## 4. Delivery 桥

`app/backends/delivery/client.py` → `DeliveryToolClient.call(name, payload)`：

- 轻工具：进程内 `run(payload)`  
- 重工具：conda 子进程（`protein_embed` / `rna` / `rhobind` / `af3`），子环境清洗 agent `.venv`

`mapping.yaml` 为编排清单；`tool_mapping.py` 对照 delivery `registry.json` 闭门失败。路径与 AF3 解释器由 `apply_delivery_env()` 解析。

---

## 5. 评估、自演进、promote

离线调参（非自主发现）：归因工具、重拟合融合/弃权/`tau_drop`、写 candidate、消融、更新 proxy cache。部署为人工 `promote-evolved`。

| 部件 | 说明 |
|------|------|
| Light LOO | `rbp_eval/loo/loo_eval.py`（CSV 经 `resolve_loo_csvs()`） |
| Heavy LOO | `rbp_eval/loo/heavy_loo.py` |
| Evolve | `rbp_eval/evolve/` → `config/evolved.candidate.yaml` |
| Runtime 旋钮 | `defaults.yaml` deep-merge `evolved.yaml`（当 `evolved: true`） |

**Promote 证据（正常路径）：** light LOO 报告通过；evolve `n≥10` 且 `delta_auprc>0`；真实 `transfer_calibration`；RNA 轴未就绪时拒绝非零 RNA 融合权重。详情：[docs/product/SELF_EVOLUTION.zh.md](docs/product/SELF_EVOLUTION.zh.md)。

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
nanobot-bio evolve
nanobot-bio gate
nanobot-bio promote-evolved
```

---

## 6. Slim vendor（计划，非删除授权）

仓内 `nanobot/` 是 Agent Controller 运行时（提案 §6.2：SoT == runtime）。每次清理阶段需聊天批准。范围外：改 delivery 源码、改写提案。

**须保留：** `tools/core` 热路径、`tools/rbp/**`、`skills/rbp-agent/**`、agent 循环、session、providers、`app/`、`rbp_eval/`、`workspace/`、`tests/`、`config/`、`scripts/`、`artifacts/`。

**已剥离：** channels / web / webui / 外部 cli / audio / gateway 等。  
阶段 A–D 与验收命令见英文 [ARCHITECTURE.md](ARCHITECTURE.md) §6。

| 变量 | 默认 | 说明 |
|------|------|------|
| `NANOBOT_WORKSPACE` | `workspace/` | 会话 + 记忆（§2） |
| `NANOBOT_CONFIG` | `~/.nanobot/config.json` | 仅本机；`chmod 600` |
| `NANOBOT_TOOL_ALLOW` | `rbp` | 勿随意放宽 |
| `NANOBOT_TOOL_PLUGINS` | off | `1`/`true` 启用 entry-points |

---

## 7. 发版清单

版本 SoT：`pyproject.toml`（semver）。README badge 与 `nanobot-bio --version` 跟随之。历史：[CHANGELOG.md](CHANGELOG.md)。

```bash
git checkout main && git pull
# bump pyproject.toml + README badges；收尾 CHANGELOG
nanobot-bio gate
bash scripts/ci/check_secrets.sh
git add pyproject.toml README.md README.zh.md CHANGELOG.md
git commit -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main && git push origin vX.Y.Z
```

若发版依赖新 delivery 快照，在 CHANGELOG 注明 bundle id，并在 [INSTALL.zh.md](INSTALL.zh.md) §3 更新布局说明。
