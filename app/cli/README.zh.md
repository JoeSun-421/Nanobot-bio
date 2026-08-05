# app/cli/

`nanobot-bio` / `rbp-agent` 的 argparse 产品 CLI。

[English](README.md) · [中文]

## 用途

本包是控制台脚本与 `python -m app` 共用的薄而稳定的命令面。处理器按组划分，使日常 chat、科学验收、离线 evolve 与工程门禁可独立演进，且不改公共命令名。这里**不实现**科学打分——处理器委托给 `app.agent`、`rbp_eval.*`、`app.dev.*` 或 delivery。

## 布局



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

| 文件 | 领域（稳定命令名） |
|------|-------------------|
| `parser.py` | 构建 argparse；**名称保持稳定** |
| `user.py` | `doctor`、`onboard`、`nanobot-smoke`、`agent`、`chat` |
| `accept.py` | `own-head` / `accept-golden`、`accept-llm`、`gap-closure` |
| `eval_cmds.py` | `run-eval`、`heavy-loo`、`evolve*`、`eval-plan`、`promote-evolved` |
| `maint.py` | `gate`、`layout`、`mvp`、`compliance` |
| `common.py` | 环境 / `sys.path` 引导（导入有意带副作用） |
| `__init__.py` | `main()`、`build_parser()` — `[project.scripts]` 入口 |
| `__main__.py` | `python -m app.cli` |

## 入口

```bash
nanobot-bio --help
python -m app --help
python -m app.cli --help
```

```python
from app.cli import main, build_parser

raise SystemExit(main(["doctor"]))
# 或查看 flags：
build_parser().print_help()
```

## 代码示例

**日常用户路径**

```bash
source scripts/nbio.sh                 # 可选日常激活
nanobot-bio doctor                  # 能力表；--verbose 打印路径
nanobot-bio onboard                 # 交互式 LLM 配置
nanobot-bio chat                    # 多轮
nanobot-bio agent --example --query "Does PTBP1 bind this RNA?"
```

**验收 / 评估 / 维护**

```bash
nanobot-bio own-head                # delivery own-head（无 LLM）
nanobot-bio accept-llm
nanobot-bio run-eval
nanobot-bio heavy-loo
nanobot-bio evolve --dry-run
nanobot-bio gate                    # 工程：ruff + pytest + layout
bash scripts/ci/ci_gate.sh          # → python -m app gate
```

**常用 flags**（`parser.py` / `user.py`）：

- `agent` / `chat`：`--device auto|cuda|cpu`、`--query`、`--rna-file`、`--example`
- `onboard`：`--provider` / `--model` / `--key`（密钥进 `.env`；配置保留 `${VAR}`）
- `gate`：仅工程——见 [`../dev/`](../dev/README.zh.md)

认证编排：[`scripts/cert/certify.sh`](../../scripts/cert/README.zh.md)。

## 依赖 / 环境

- 同 [`app/`](../README.zh.md)：editable install；科学命令需要 delivery。
- 导入 `app.cli.common` 会有意引导路径——嵌入 `main()` 时请保留该副作用。

## 设计思路

- 薄 argparse，产品 UX 变更不必牵动 Nanobot API。
- 拆分 user / accept / eval / maint，便于 CI 不加载 chat UX。
- CLI 层绝不编造分数。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../dev/README.zh.md`](../dev/README.zh.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../../scripts/ci/README.zh.md`](../../scripts/ci/README.zh.md)
