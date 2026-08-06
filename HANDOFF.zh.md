# Nanobot-bio — 协作者交接文档

**读者。** 接手本仓库（或同级科学工具包）的工程师，需要在几分钟内建立正确心智模型。

**配对文档。** Delivery 科学工具包：[`../rhobind_agent_delivery/agent/HANDOFF.md`](../rhobind_agent_delivery/agent/HANDOFF.md)。产品约束：[`AGENTS.md`](AGENTS.md)。分层：[`ARCHITECTURE.zh.md`](ARCHITECTURE.zh.md)。安装：[`INSTALL.zh.md`](INSTALL.zh.md)。

**版本。** 包名 `nanobot-bio` **0.5.1**（`pyproject.toml`）。CLI 入口：`nanobot-bio` 与 `rbp-agent` → `app.cli:main`。

---

## 本仓库是什么

面向 **RNA–RBP 结合预测** 的命令行 Agent：给定 RBP + RNA → 类型约束 JSON 结论（`label`、`confidence`、`p_hat`、`explanation`、`supporting_rbps`）。

| 模式 | 何时 | 做什么 |
|------|------|--------|
| **Own-head** | 目标 RBP 在 panel 内且有 RhoBind head | 对该 head 打分后结束 |
| **Transfer** | panel 外 / 未见 | 多模态检索供体 → 对供体 `predict_interaction` → `similarity_weighted_vote` |

阶段 **0→1→2→3** 与工具纪律见 [`nanobot/skills/rbp-agent/SKILL.md`](nanobot/skills/rbp-agent/SKILL.md)。LLM **绝不**编造 `p_hat` / motif / 注释。

---

## 磁盘布局（本机 / 可移植）

```text
$BIO_ROOT/                          # 如 ~/bio_agent 或 /workspace/.../bio_agent
  Nanobot-bio/                      # 本仓库（GitHub 目录名；包名 = nanobot-bio）
  rhobind_agent_delivery/           # 科学工具 + DB + release（Agent 只读）
  rhobind_testdata_v2/              # 可选；LOO 扩充数据
```

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}"
source scripts/nbio.sh              # 或：./scripts/nbio.sh start
```

- 检出目录常见为 **`Nanobot-bio`**（大写 N）。若克隆为小写 `nanobot-bio` 亦可。
- 优先用 `NANOBOT_BIO_ROOT`，或 `cd` 到含 `scripts/nbio.sh` 的树；勿写死试验机绝对路径。
- **禁止**从本 Agent 修改 `rhobind_agent_delivery/`；科学调用只经 `app/backends/delivery`。

---

## 60 秒上手

```bash
./scripts/nbio.sh setup             # 一次：.venv + delivery conda
nanobot-bio onboard                 # LLM 厂商 + key → .env（无默认厂商）
./scripts/nbio.sh start             # 路径发现 → 纠偏 AF3/.env → chat
nanobot-bio doctor                  # 能力矩阵
nanobot-bio agent --example pos     # 金标一次性预测（无需自备 RNA）
```

仅激活不进 chat：`source scripts/nbio.sh`。

---

## 分层（谁负责什么）

```text
CLI (app/cli)  →  RBPAgent (app/agent.py)
                    →  nanobot/  (loop · skill · tools SoT)
                         →  app.backends.delivery  （只读桥）
                              →  rhobind_agent_delivery/
离线评估 / 自演进  →  rbp_eval/   （不在 chat 热路径）
```

| 目录 | 角色 |
|------|------|
| `app/` | 产品壳：CLI、verdict 解包、onboard、能力矩阵、delivery 客户端 |
| `nanobot/` | 仓内精简 Nanobot，**SoT == 运行时**；`import nanobot` 必须解析到这里。**禁止** `pip install nanobot-ai` |
| `nanobot/skills/rbp-agent/` | Skill SoT；改完后 `python -m app.sync_overlay` 同步到 workspace |
| `nanobot/agent/tools/rbp/` | 产品工具类 |
| `rbp_eval/` | LOO / accept / evolve / scoring（物理路径 = import 路径） |
| `config/` | `defaults.yaml` + 演化候选 |
| `scripts/nbio.sh` | 可移植入口：setup / start / status / doctor / chat |
| `workspace/` | 运行时 skill 覆盖 + 指向 `artifacts/` 的符号链接 |
| `artifacts/` | 规范会话 / 记忆 / 产物目录（数据本身 gitignore） |

---

## 硬性约束（摘自 AGENTS.md）

**禁止**

- 改 delivery；用 LLM 编造 `p_hat`；对未见目标在无供体时直接 `predict_interaction`。
- 把 AF3/结构 miss 当相似度 `0`；未经门禁 + nested-split 就 promote 演化配置。
- 再建第三套 tools 树；安装 PyPI `nanobot-ai`；把科学栈 torch 导入 nanobot 进程。
- 用历史会话 / 转录里的工具结果当作权威分数跳过 Stage 0–3。

**必须**

- 经 `nanobot-bio` / `rbp-agent` / `python -m app` 进入。
- 遵守 Stage 0→1→2→3；in-panel 走 own-head；\(N_{\mathrm{cand}}\le5\)；融合相似度 \(<0.30\) 丢弃。
- Transfer 的 `p_hat` 权威 = delivery `similarity_weighted_vote`（非 LLM max/mean）。
- 改 skill/tools 后：`python -m app.sync_overlay`，再跑 `pytest tests/test_proposal_compliance.py tests/test_package_layout.py`。

---

## 随仓文档 vs 本机私有

| 随仓（git 内） | 本机私有（`docs/` 已 gitignore） |
|----------------|----------------------------------|
| README、INSTALL、ARCHITECTURE、AGENTS、CHANGELOG、HANDOFF | 原 `docs/product/*`、`docs/guides/*` 产品指南 |
| 各包 `README.md` / `README.zh.md` | 飞书 / 提案草稿 |
| `nanobot/skills/rbp-agent/SKILL.md` | |

若某 README 仍写 `docs/…`，视为过时；改看 SKILL / ARCHITECTURE / 包 README。

---

## Docker 注意

`docker-compose.yml` 服务名是 **`app`**、**`app-full`**、**`doctor`**（没有名为 `chat` 的服务）。

```bash
docker compose up app                          # agent profile
docker compose --profile full up app-full      # science profile
docker compose run --rm doctor
```

已知分歧：部分 Docker 构建曾假设小写 `nanobot-bio/` 同级目录，或克隆上游 Nanobot。除非你已验证镜像，优先用主机 `./scripts/nbio.sh` + 仓内 `nanobot/` SoT。见 [`INSTALL.zh.md`](INSTALL.zh.md) Path B 与 [`scripts/docker/README.zh.md`](scripts/docker/README.zh.md)。

---

## 常用 CLI

| 目标 | 命令 |
|------|------|
| 对话 / 一次性 | `nanobot-bio chat` · `nanobot-bio agent` |
| 能力 / 路径 | `nanobot-bio doctor [--verbose]` |
| Own-head 验收 | `nanobot-bio accept-golden` |
| LLM 验收 | `nanobot-bio accept-llm` |
| LOO / 演进 | `nanobot-bio run-eval` · `heavy-loo` · `evolve` · `promote-evolved` |
| 工程门禁 | `nanobot-bio gate` · `bash scripts/ci/ci_gate.sh` |
| 认证 / transfer | `bash scripts/cert/certify.sh` · `python -m rbp_eval.accept.transfer_calibration` |

完整列表：`nanobot-bio --help`。

---

## 下一步阅读

1. 本文 + [`AGENTS.md`](AGENTS.md)
2. [`INSTALL.zh.md`](INSTALL.zh.md) — 环境变量、conda、AF3、Docker
3. [`ARCHITECTURE.zh.md`](ARCHITECTURE.zh.md) — 记忆/会话、桥接、发版
4. [`nanobot/skills/rbp-agent/SKILL.md`](nanobot/skills/rbp-agent/SKILL.md) — 阶段规则
5. Delivery 交接：`rhobind_agent_delivery/agent/HANDOFF.md` + `SETUP.md` + `tools/registry.json`

English: [HANDOFF.md](HANDOFF.md).
