# app/

产品外壳：CLI、`RBPAgent` 组装、delivery 桥与运行时配置。**本层不算 `p_hat`**。

[English](README.md) · [中文]

## 功能

- 暴露稳定命令 `nanobot-bio` / `rbp-agent`（`python -m app`）：chat、一次性 agent、doctor、onboard、验收、评估与工程门禁
- 组装 `RBPAgent`（`agent.py`）：对接仓内 Nanobot、过滤工具、规范化 JSON verdict
- 科学 I/O 一律经 [`backends/delivery/`](backends/delivery/README.zh.md) 只读调用同级 `rhobind_agent_delivery`
- 管理路径、onboard、能力诚实矩阵、verdict schema、SoT → workspace 同步

## 实现方法

| 路径 | 角色 |
|------|------|
| `__main__.py` | `python -m app` → CLI |
| `agent.py` | `RBPAgent`：会话 / 工具过滤 / Nanobot 集成 / verdict 解包 |
| [`cli/`](cli/README.zh.md) | argparse 命令分组（user / accept / eval / maint） |
| [`backends/delivery/`](backends/delivery/README.zh.md) | `DeliveryToolClient`、`mapping.yaml`、环境解析 |
| `core/` | `paths`、`runtime_config`、`capability_matrix`、`verdict_schema`、`onboard`、`chat_ux` 等 |
| `dev/` | `gate` / `layout` / `mvp` / `compliance`（工程门禁，非科学打分） |
| `sync_overlay.py` | SoT skill/tools → 运行时 + `workspace/skills` |
| `dotenv_util.py` | 加载仓库根 `.env` |
| `sot.py` / `integrate.py` | SoT 辅助；优先用 `app.agent`，避免依赖旧 `integrate` |

分层（见 [`ARCHITECTURE.md`](../ARCHITECTURE.md) §1）：

```
用户 CLI (app/cli)
  → app.agent.RBPAgent
      → nanobot/ (loop · tools · skill)
          → app.backends.delivery
              → ../rhobind_agent_delivery (只读)
离线评估 → rbp_eval/（不经 chat 主路径）
```

## 怎么使用

```bash
nanobot-bio doctor|chat|agent|onboard|gate|…
# 等价：
python -m app doctor
rbp-agent chat
```

安装入口见 [`scripts/setup/`](../scripts/setup/README.zh.md)；安装细节 [`INSTALL.md`](../INSTALL.md)；约束 [`AGENTS.md`](../AGENTS.md)。

改完 `nanobot/` 下的 skill / RBP tools 后：

```bash
python -m app.sync_overlay
# 或：nanobot-bio doctor
```

## 设计思路

- **职责分离：** App 只编排；RhoBind / Foldseek / AF3 留在 delivery。LLM 不得编造 `p_hat`、motif 或注释。
- **命令名稳定：** 协作方与 CI 依赖 `cli/parser.py` 中的 argparse 命令名。
- **单一 import 根：** `NANOBOT_SRC` / `sys.path` 优先仓内 `nanobot/`，避免被 PyPI `nanobot-ai` 抢包。
- **能力诚实：** AF3 / peaks 缺失走 `capability_matrix` caveat，而不是伪造相似度 `0`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`INSTALL.md`](../INSTALL.md) · [`../nanobot/README.zh.md`](../nanobot/README.zh.md) · [`../artifacts/README.zh.md`](../artifacts/README.zh.md)
