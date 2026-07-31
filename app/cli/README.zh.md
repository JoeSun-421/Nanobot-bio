# app/cli/

`nanobot-bio` / `rbp-agent` 的 argparse 产品 CLI。

[English](README.md) · [中文]

## 功能

- 稳定的命令面：console_scripts 与 `python -m app` 共用
- 分组实现：日常用户命令、验收、离线评估/演化、工程维护
- `common.py` 提供共享 bootstrap（环境 / `sys.path` / 路径）

## 实现方法

| 文件 | 命令域（稳定名） |
|------|------------------|
| `parser.py` | 构建 argparse；**命令名保持稳定** |
| `user.py` | `agent`、`chat`、`onboard`、`doctor`、`nanobot-smoke` |
| `accept.py` | `accept-golden` / `own-head`、`accept-llm`、`gap-closure` |
| `eval_cmds.py` | `run-eval`、`heavy-loo`、`evolve*`、`eval-plan`、`promote-evolved` |
| `maint.py` | `gate`、`layout`、`mvp`、`compliance` |
| `common.py` | 环境 / 路径 bootstrap（import 即有副作用） |
| `__init__.py` | `main()`；`pyproject` scripts 指向此处 |

入口：`pyproject.toml` 的 `[project.scripts]` → `app.cli:main`。

## 怎么使用

```bash
nanobot-bio --help
nanobot-bio doctor              # 功能能力表；--verbose 看路径明细
source scripts/nbio             # 日常激活（见 scripts/nbio）
python -m app chat
bash scripts/ci/ci_gate.sh          # → python -m app gate
```

常用参数：

- `agent` / `chat`：`--device auto|cuda|cpu`，`--query` / `--rna-file` / `--example`
- `onboard`：交互式，或 `--provider` / `--model` / `--key`（密钥进 `.env`，config 只存 `${VAR}`）
- `gate`：工程门禁（ruff + pytest + layout）；见 `scripts/ci/`

认证编排在 [`scripts/cert/certify.sh`](../../scripts/cert/README.zh.md)（内部调 doctor / accept）。

## 设计思路

- CLI 保持薄层，避免产品 UX 变动牵动 Nanobot API。
- user / accept / eval / maint 分文件，便于 CI 只跑 maint/accept。
- 本层不算科学分——委托给 `app.agent`、`rbp_eval.*` 或 delivery。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../scripts/ci/README.zh.md`](../../scripts/ci/README.zh.md)
