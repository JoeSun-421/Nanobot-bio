# app/

产品外壳：CLI、`RBPAgent` 组装、delivery 桥与运行时配置。**本层不算 `p_hat`**。

[English](README.md) · [中文]

## 用途

`app/` 是 **nanobot-bio** 面向操作者的产品层。它对接仓内 Nanobot 运行时、为 RBP 科学模式过滤工具、规范化 JSON verdict，并把每一次科学调用经只读 delivery 客户端桥出。协作者与 CI 应从这里进入（`nanobot-bio` / `rbp-agent` / `python -m app`），而不是临时直连 Nanobot 或 delivery 脚本。

离线评估与自演化在 [`rbp_eval/`](../rbp_eval/README.zh.md)，刻意不在 chat 热路径上。绑定阶段语义（Stage 0 own-head、transfer、integrate）见 [`docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md)。



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

## 布局

| 路径 | 角色 |
|------|------|
| `__main__.py` | `python -m app` → CLI |
| `agent.py` | `RBPAgent` / `AgentResult`：会话、工具过滤、Nanobot 集成、verdict 解包 |
| [`cli/`](cli/README.zh.md) | argparse 命令分组（user / accept / eval / maint） |
| [`backends/`](backends/README.zh.md) · [`backends/delivery/`](backends/delivery/README.zh.md) | `DeliveryToolClient`、`mapping.yaml`、环境解析 |
| [`core/`](core/README.zh.md) | paths、runtime_config、capability_matrix、verdict_schema、onboard、chat_ux |
| [`dev/`](dev/README.zh.md) | gate / layout / mvp / compliance（工程门禁，非科学打分） |
| [`bootstrap/`](bootstrap/) | SoT 定位、`sync_overlay`、工具安装（无 `app.agent` 环） |
| `sync_overlay.py` | 唯一根级兼容入口（`python -m app.sync_overlay` → bootstrap） |
| `dotenv_util.py` | 加载仓库根 `.env` |

分层（[`ARCHITECTURE.md`](../ARCHITECTURE.md) §1）：

```
用户 CLI (app/cli)
  → app.agent.RBPAgent
      → nanobot/ (loop · tools · skill)
          → app.backends.delivery
              → ../rhobind_agent_delivery (只读)
离线评估 → rbp_eval/（不经 chat 主路径）
```

## 入口

控制台脚本（`pyproject.toml`）：`nanobot-bio`、`rbp-agent` → `app.cli:main`。

```bash
nanobot-bio doctor|chat|agent|onboard|gate|…
python -m app doctor
rbp-agent chat
```

## 代码示例

**CLI 一次性 agent**

```bash
# 先激活环境（见 INSTALL.md / scripts/nbio）
nanobot-bio doctor
nanobot-bio agent --query "Does this RNA bind PTBP1?" --example
# 或指定 RNA 文件：
nanobot-bio agent --rna-file /path/to/rna.fa --query "Predict binding to PTBP1"
```

**编程调用 `RBPAgent`**

```python
from app.agent import RBPAgent

agent = RBPAgent()  # 应用 delivery 环境并注册 RBP tools
result = agent.run_sync("Predict whether the sample RNA binds PTBP1.")
print(result.verdict_valid, result.verdict)
print(result.tools_used)
# 异步：
# result = await agent.run("…")
```

**改完 skill / RBP tools 后同步 SoT**

```bash
python -m app.sync_overlay
# 等价：python -m app.bootstrap.sync_overlay
nanobot-bio doctor
```

## 依赖 / 环境

- 本仓库 editable install + 经 `nanobot-bio onboard` 配置的 LLM 密钥（`.env` / `~/.nanobot/config.json`）。
- 科学路径需要同级 `rhobind_agent_delivery`（或 `DELIVERY_ROOT`）及 mapping 中的 conda 环境。
- `NANOBOT_SRC` / `sys.path` 优先仓内 `nanobot/`，避免被 PyPI `nanobot-ai` 抢包。

安装：[`scripts/setup/`](../scripts/setup/README.zh.md) · [`INSTALL.md`](../INSTALL.md)。约束：[`AGENTS.md`](../AGENTS.md)。

## 设计思路

- **职责分离：** App 只编排；RhoBind / Foldseek / AF3 留在 delivery。LLM 不得编造 `p_hat`、motif 或注释。
- **命令名稳定：** 协作方与 CI 依赖 `cli/parser.py` 中的 argparse 命令名。
- **能力诚实：** AF3 / peaks 缺失走 `capability_matrix` caveat，而不是伪造相似度 `0`。
- **禁止跨层合并：** 不要把 `app/` 并入 `nanobot/`、`rbp_eval/` 或 `nanobot/agent/tools/rbp`。产品壳、框架 SoT、离线评估、只读 delivery 必须分家；权威入口为 `app.bootstrap` / `app.agent`，根上仅保留 `sync_overlay` 兼容模块。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../nanobot/README.zh.md`](../nanobot/README.zh.md) · [`../artifacts/README.zh.md`](../artifacts/README.zh.md)
