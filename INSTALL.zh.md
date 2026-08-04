# 安装指南（协作方入门）

<p><a href="INSTALL.md">English</a> · <b>中文</b></p>

> **安装 / 环境 / 验收的单一入口。** 产品概览见 [README.zh.md](README.zh.md) / [README.md](README.md)；架构见 [ARCHITECTURE.zh.md](ARCHITECTURE.zh.md) / [ARCHITECTURE.md](ARCHITECTURE.md)；Agent 门禁见 [AGENTS.md](AGENTS.md)。

## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
# 惯例（可由 nbio 发现，也可显式 export）：
#   DELIVERY_ROOT=$BIO_ROOT/rhobind_agent_delivery
#   RHOBIND_RELEASE=$DELIVERY_ROOT/release/rhobind_release_v1
#   RBP_TEST_DATA_ROOT=$BIO_ROOT/rhobind_testdata_v2/rhobind_testdata_v2/test_data
```

勿把某一台试验机的绝对路径当作唯一真相；`nbio` 在本机自动搜寻。

---

## 0. 前置条件

| 项 | 要求 | 说明 |
|----|------|------|
| OS | Linux x86_64（Ubuntu 20.04+ 验证通过） | macOS/WSL 可跑 agent 层，科学栈未验证 |
| 磁盘 | ≥ 30 GB 空闲 | delivery bundle ~15 GB；conda 科学栈 ~10 GB |
| Python | ≥ 3.10（推荐 3.13） | 仓内精简 nanobot 与本机 venv 同解释器 |
| conda / mamba | full 路径必需；agent 路径可选 | 推荐 mamba 加速 |
| GPU | 可选 | rhobind_predict / ESM / AF3 受益；CPU 可跑 doctor + chat |
| LLM API key | `agent` / `chat` / `accept-llm` 必需 | `nanobot-bio onboard` 显式选厂商；密钥写入 `.env` |

---

## 1. 三条安装路径

### 路径 A：一键脚本（最快，推荐首次使用）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
# delivery bundle 需单独获取（见 §3），与 nanobot-bio 同级：
#   $BIO_ROOT/nanobot-bio/
#   $BIO_ROOT/rhobind_agent_delivery/
cd "$BIO_ROOT/nanobot-bio"

./scripts/nbio setup                  # full 科学栈 + agent venv（= setup_all.sh）
# 已知机型也可显式选（薄包装，内部仍调 setup_all.sh）：
# bash scripts/setup/setup_all_ampere_or_older.sh   # A100/H100/4090… → 经典 af3
# bash scripts/setup/setup_all_blackwell.sh         # RTX 5090 / CC12 → af3_blackwell
# 或仅 agent 层（无 conda）：
# ./scripts/nbio setup --skip-conda

nanobot-bio onboard                   # 显式选择 LLM 厂商 + key（写入 .env）
./scripts/nbio start                  # 日常万能一键：纠偏 AF3 → chat
# ./scripts/nbio start --dry-run      # 只看路径/GPU 适配（可顺带 heal .env）
# source scripts/nbio && nanobot-bio doctor   # 分步：激活 + 能力表
```

`setup_all.sh`（经 `nbio setup`）使用仓内精简 `nanobot/`。`pip install -e .` 会安装 in-repo 包；勿再安装 `nanobot-ai`（会抢 `import nanobot`）。按 GPU 选型说明见 [docs/guides/AF3_RUNTIME_AND_RELEASE.zh.md §3.4](docs/guides/AF3_RUNTIME_AND_RELEASE.zh.md)。脚本分类见 [`scripts/README.md`](scripts/README.md)；单一入口见 [`scripts/nbio`](scripts/nbio)。

**环境名存在 ≠ 依赖已齐。** delivery `setup_envs.sh` 只在 conda **名字缺失**时创建；裸 `conda create -n rhobind` 会留下空壳。`nbio setup` / `setup_all.sh` 会做 **import 级校验**并 heal。日常用 `./scripts/nbio start`（或 `source scripts/nbio` + `nanobot-bio chat`），**不必每次** setup。`start` 在本机**自动搜寻** AF3 / conda 路径（`$AF3_BLACKWELL_ROOT`、BIO 旁 `af3_blackwell`、`~/af3_blackwell`、`conda info --base` 等；AutoDL 布局只是候选之一），CC12 上纠偏 classic→blackwell，默认备份后改写 `.env`。用 `start --dry-run` 可只看候选列表。兼容旧命令：`source scripts/setup/activate_env.sh`（转发到 `nbio`）。

### 路径 B：Docker（隔离环境，推荐给只跑不开发的协作方）

```bash
cd nanobot-bio
# agent-only 镜像（轻）
docker compose build
# 或 full 科学栈镜像（重，需 GPU）
docker compose --profile full build

# 把 LLM 配置挂进去（首次需先在宿主机 onboard，或直接挂 config）
docker compose run --rm app onboard

# 自检 + 交互式 chat
docker compose run --rm app doctor
docker compose up app                # = nanobot-bio chat
```

数据 bundle 通过 volume 挂载（见 `docker-compose.yml`），不烤进镜像。详见 [Dockerfile](Dockerfile) 头部注释。

### 路径 C：手动 venv + conda（精细控制）

> 注意：仅跑 `setup_envs.sh` **不会**修复已存在的空壳 env。装完后请用  
> `conda run -n rhobind python -c "import torch, transformers"` 自检，或改走路径 A 的 `setup_all.sh`。

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"

# 1. delivery 科学栈 conda envs
cd "$BIO_ROOT/rhobind_agent_delivery"
bash agent/setup_envs.sh             # protein_embed / rna / rhobind / af3

# 2. agent venv（仓内已含精简 nanobot/）
cd "$BIO_ROOT/nanobot-bio"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip uninstall -y nanobot-ai nanobot 2>/dev/null || true
pip install -e ".[dev]"

# 3. 校验 import 指向本仓 + workspace skill 链接
python -c "import nanobot; print(nanobot.__file__)"   # 必须含 nanobot-bio/nanobot
python -m app.sync_overlay
cp .env.example .env                # 按需编辑；NANOBOT_SRC 默认本仓 nanobot/
nanobot-bio doctor
```

---

## 2. 环境变量总表

合并自 [README §6](README.md)、[`.env.example`](.env.example)、[`app/backends/delivery/env.py`](app/backends/delivery/env.py)、delivery `setup.sh`。`apply_delivery_env()` 会为缺失项填默认值，所以**只有覆盖默认时才需手动设**。

| 变量 | 默认 | 必填 | 用途 |
|------|------|------|------|
| `BIO_ROOT` | `nanobot-bio/..` | 否 | 仓库父目录 |
| `DELIVERY_ROOT` | `$BIO_ROOT/rhobind_agent_delivery` | 是* | delivery 包根 |
| `NANOBOT_SRC` | `$NANOBOT_BIO_ROOT/nanobot` | 是* | 仓内精简 nanobot 运行时（SoT == runtime） |
| `NANOBOT_BIO_ROOT` | `nanobot-bio/` | 否 | app 包根 |
| `NANOBOT_WORKSPACE` | `$NANOBOT_BIO_ROOT/workspace` | 否 | nanobot 工作区（会话/记忆路径见 [ARCHITECTURE.md](ARCHITECTURE.md) §2） |
| `NANOBOT_CONFIG` | `~/.nanobot/config.json` | 是** | LLM provider/model + `${…_API_KEY}` 引用（密钥在 `.env`） |
| `AGENT_DB` | `$DELIVERY_ROOT/agent_db` | 否 | registry / embeddings / DBs |
| `RBP_REGISTRY` | `$AGENT_DB/registry/rbp_registry.json` | 否 | 238 条 RBP 注册表 |
| `RHOBIND_RELEASE` | `$DELIVERY_ROOT/release/rhobind_release_v1` | 否 | 预测器 checkpoint |
| `RBP_PROTEINS` | `$DELIVERY_ROOT/reference` | 否 | 参考蛋白/结构 |
| `AFDB_DIR` | `$RBP_PROTEINS/structures/afdb` | 否 | AFDB PDB 目录 |
| `TRANSFER_DIR` | `$AGENT_DB/transfer` | 否 | LOO transfer CSV |
| `EMB_BANK` | `$AGENT_DB/embedding_bank` | 否 | ESM embedding 库 |
| `FOLDSEEK_DB` | `$AGENT_DB/foldseek_db/refs` | 否 | foldseek 索引 |
| `SEQ_DB` | `$AGENT_DB/seq_db/refs` | 否 | mmseqs 序列索引 |
| `PEAKS_DB` | `$AGENT_DB/peaks_db/peaks` | 否 | peaks 索引 |
| `USALIGN` | `$AGENT_DB/bin/USalign` | 否 | 结构对齐二进制 |
| `AF3_DIR` | `$DELIVERY_ROOT/agent/third_party/alphafold3` | 否 | AF3 源码 |
| `AF3_PARAMS` | `$DELIVERY_ROOT/af3_assets/alphafold_param` | 否 | AF3 权重 |
| `AF3_PYTHON` | conda `af3` env python | 否 | AF3 解释器 |
| `RHOBIND_DEVICE` | `auto` | 否 | `auto`/`cuda`/`cpu` |
| `RBP_BACKEND` | `delivery` | 否 | 工具后端 |
| `RBP_LLM_PROVIDER` | （无默认） | 否\*\* | 显式选择的厂商名；`onboard` 写入 `.env` |
| `RBP_LLM_MODEL` | （无默认） | 否\*\* | 对应模型 id |
| `OPENAI_API_KEY` 等 | — | 否\*\* | 各厂商密钥只放 `nanobot-bio/.env`；config 写 `${VAR}` |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 否 | HF 镜像（ESM 权重） |
| `OMP_NUM_THREADS` | `4` | 否 | 科学工具线程数 |

\* `setup_all.sh` / Docker 会自动设；手动路径需自己 export。
\** `onboard` 写入 `.env`（密钥）与 `~/.nanobot/config.json`（provider/model + `${…_API_KEY}` 引用）；无默认厂商，需显式选择。

`RNA_FM_CHECKPOINT` 对当前 delivery **不适用（N/A）**。RNA 证据来自
`rna_blastn` 与 `PEAKS_DB`；不要为了“启用 RNA 轴”伪造 RNA-FM 路径或权重。

工作区落盘、slim vendor 残留与工具 allowlist 说明统一见 [ARCHITECTURE.md](ARCHITECTURE.md) §2 / §6。

**RTX 5090 / Blackwell（CC 12）：** 交付钉死的 `af3`（jax 0.4.34）无法推理。不改 delivery，另装并行栈。推荐整机入口：

```bash
bash scripts/setup/setup_all_blackwell.sh    # = setup_all.sh --af3-stack=blackwell
# 若只需补装 AF3 隔离栈（不动 agent venv）：
# bash scripts/setup/setup_af3_blackwell.sh
```

然后让本机路径写入 `.env`（权重仍用 delivery 的 `AF3_PARAMS`）。**不要**手抄试验机 AutoDL 绝对路径；用发现结果：

```bash
./scripts/nbio start --dry-run    # 查看本机 AF3_BLACKWELL_ROOT / AF3_PYTHON 候选
./scripts/nbio start --heal       # 将本机探测路径写入 .env（先备份）
# 或手动（示例占位，换成 dry-run 打印的路径）：
# AF3_DIR=$AF3_BLACKWELL_ROOT/alphafold3
# AF3_PYTHON=$(conda info --base)/envs/af3_blackwell/bin/python
# AF3_PARAMS=$DELIVERY_ROOT/af3_assets/alphafold_param
# AF3_CACHE=$AF3_BLACKWELL_ROOT/alphafold_cache
```

成功后 AF3 状态文件（默认 `~/.cache/nanobot-bio/af3_status`，可用 `AF3_STATUS_FILE` 覆盖；不再写入仓内）应为 `state=ok`（否则 agent 会把结构轴标成 deferred）。
`setup_all.sh`（`AF3_STACK=auto`）会检测 CC 12 并自动选择这个隔离环境；非 5090 机用 `setup_all_ampere_or_older.sh` 强制经典 `af3`。均不覆盖 delivery 的官方 `af3` 环境。

版本矩阵、ColabFold MSA 限制与发行改进清单见 [docs/guides/AF3_RUNTIME_AND_RELEASE.zh.md](docs/guides/AF3_RUNTIME_AND_RELEASE.zh.md) · [EN](docs/guides/AF3_RUNTIME_AND_RELEASE.md)。

---

## 3. 数据获取

delivery bundle（`rhobind_agent_delivery/`）含全部数据：238 条 registry、embedding 库、foldseek/mmseqs 索引、AFDB 结构、LOO transfer 矩阵、rhobind checkpoint、AF3 权重。

**两条获取路径：**

- **已有 bundle**（推荐）：从协作方处获取 `rhobind_agent_delivery/` 目录，放到 `$BIO_ROOT/` 下与 `nanobot-bio/` 同级。
- **从零重建**：见 [`rhobind_agent_delivery/agent/database/SOURCES.md`](../rhobind_agent_delivery/agent/database/SOURCES.md)（记录了 pc157 构建过程：`build_registry.py` / `build_embedding_bank.py` / foldseek / mmseqs）。重建脚本见 [`scripts/data/bootstrap_data.sh`](scripts/data/bootstrap_data.sh)（幂等）。

数据路径全部由上表环境变量驱动，bundle 放哪都行，只要 `DELIVERY_ROOT` / `AGENT_DB` 指对。

---

## 4. 验收流程

**权威验收路径：`nanobot-bio accept-golden`**（覆盖 delivery 原生 smoke 的断言）。

完整的无 LLM/无密钥认证入口：

```bash
bash scripts/cert/certify.sh --full
```

该命令写出环境/不可变输入 checksum、registry 工具场景、own-head 与
transfer 报告；不会读取或输出 provider API key。

```bash
nanobot-bio doctor           # 1. 环境自检（路径/registry/skill/axes/AF3）
nanobot-bio accept-golden    # 2. own-head golden（PTBP1 × pos RNA ≈ 0.966）
nanobot-bio accept-llm       # 3. LLM touchpoint（需 API key）
nanobot-bio gap-closure      # 4. Stage-0 / unseen fixture 证据包
nanobot-bio gate             # 5. 工程门（ruff + pytest + layout + 可选 LOO）
```

delivery 原生 `agent/examples/run_example.sh` 仅用于**无 app 层时的回归**（直接调 delivery 脚本），协作方验收请走 `nanobot-bio accept-golden`。

报告输出到 `artifacts/reports/{json,md,csv}/`（或 `~/.nanobot-bio/artifacts/reports/` 当 env 覆盖时）。会话 / PA 记忆 / 领域记忆（proxy_map）规范路径见 [`docs/guides/MEMORY_AND_SESSIONS.zh.md`](docs/guides/MEMORY_AND_SESSIONS.zh.md) · [EN](docs/guides/MEMORY_AND_SESSIONS.md)（`workspace/sessions|memory` 仅为 symlink）。

### 4.1 CI 与 self-hosted runner

`.github/workflows/ci.yml` 有三个 job：

| job | runner | 触发 | 作用 |
| --- | --- | --- | --- |
| `test` | `ubuntu-latest` | 每次 push/PR | ruff + pytest + layout + secret scan（公开 CI，无需 GPU） |
| `science` | `self-hosted, linux, science` | 仅 tag / 手动 | `accept-golden`（需 delivery bundle + 内存/GPU） |
| `eval` | `self-hosted, linux, science` | 仅 tag / 手动 | Stage-3 消融 + ECE（B5） |

`science` / `eval` 只在 tag（`v*`）或 `workflow_dispatch` 时跑，**常规 push/PR 只跑 `test`**——这样没有 self-hosted runner 时 `test` 仍能保持绿色，重 job 不会无限排队。

要启用 `science` / `eval`：在一台有 delivery bundle 的机器上注册 runner 并打标签 `self-hosted, linux, science`，再设仓库 secret `DELIVERY_BUNDLE_PATH`（指向 `rhobind_agent_delivery` 绝对路径）与可选 `NANOBOT_CONFIG_PATH`。发版与 `promote-evolved` 流程见 [ARCHITECTURE.md](ARCHITECTURE.md) §5 / §7。

---

## 5. 常见问题

- **`predict_interaction` / doctor 报缺 `torch`（rhobind hollow）**：conda 环境名在，但未装 release requirements（常见于手搓 `conda create -n rhobind`）。`doctor` 会显示 `rhobind torch+transformers: MISSING` 且 `[RED] science_envs`。修复：`bash scripts/setup/setup_all.sh`（会 heal），勿只跑 delivery `setup_envs.sh`。
- **`doctor` 报 AF3 deferred/broken**：常见。Skill 规则：先 AFDB `structure_fetch`，**仅 AFDB miss** 时调 `predict_structure`（`use_af3_fallback=true`）；仅序列 / 无 accession 目标必须走 AF3 一次。失败则 caveat，序列/功能轴继续；**勿**把结构 miss 当成相似度 `0`。重跑 `bash scripts/setup/setup_all.sh`（AF3 harden 10 分钟预算）可改善探针。
- **`onboard` 后 chat 仍报 no key**：确认已显式选择厂商；密钥在 `nanobot-bio/.env`（如 `OPENAI_API_KEY=` / `DEEPSEEK_API_KEY=`），`~/.nanobot/config.json` 里是 `${…_API_KEY}` 引用而非明文；检查 `NANOBOT_CONFIG` 路径。
- **CI 跳过 own-head/LOO**：public CI 无 GPU/delivery bundle。本地跑 `bash scripts/ci/ci_gate.sh` 或 `rbp-agent gate`。
- **CI 跳过 delivery 依赖测试**：公开 `test` job 无同级 `rhobind_agent_delivery`。`tests/conftest.py` 在 `delivery_root()` 不可用时 **skip**（非整批 fail）；标记 `@pytest.mark.requires_delivery` 的用例在收集阶段也会 skip。有 bundle 时设 `DELIVERY_ROOT` 或保持同级目录即可照常跑。
- **docs/ 不在 GitHub 上**：整个 `docs/`（含 `product/proposal.md` / `product/proposal.zh.md`）本地保留、不推远程；缺省时权威文档相关测试会 skip。需要提案/清单时从协作方单独拷贝；架构与 slim 政策见根目录 [ARCHITECTURE.md](ARCHITECTURE.md)。
