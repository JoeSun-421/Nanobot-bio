# scripts/ci/

轻量 CI / 本地工程门禁（密钥扫描不需要 GPU 科学栈）。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "$BIO_ROOT/nanobot-bio" && source scripts/nbio.sh`。

## 功能

- 合并前扫描已跟踪文件中的私钥 / API key 形态
- 激活 `.venv`（若存在）后跑 `python -m app gate` 的薄包装
- 供 GitHub Actions 与本地合并前检查使用

## 实现方法

| 脚本 | 作用 |
|------|------|
| `check_secrets.sh` | 扫描 **git 跟踪文件**（非 git 时扫常见源码根）；命中则非零退出。不读取/打印 `~/.nanobot/config.json` 中的真实密钥，仅检查权限 / 是否被误 track |
| `ci_gate.sh` | `exec python -m app gate …`（即 `nanobot-bio gate` / `rbp-agent gate`） |

仓库根：`$SCRIPT_DIR/../..`。`check_secrets` 排除 lock、二进制、`artifacts/`，并跳过含 `example` / `placeholder` 的行。

工作流：[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 的 `check_secrets` job 调用本目录 `check_secrets.sh`。

## 怎么使用

```bash
bash scripts/ci/check_secrets.sh
bash scripts/ci/ci_gate.sh
bash scripts/ci/ci_gate.sh --skip-eval
bash scripts/ci/ci_gate.sh --no-cov
```

无 LLM key 的完整科学验收请用 [`../cert/`](../cert/README.zh.md)，或在有 delivery 的本机跑 `rbp-agent gate`。

## 设计思路

- 公开 CI 常无 delivery/GPU；把快速密钥 + 工程门禁与重认证分开。
- 优先扫已跟踪文件，与将要发布的内容一致。
- 本机若有 `~/.nanobot/config.json`，建议 `chmod 600`；切勿 `git add -f`。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../tests/README.zh.md`](../../tests/README.zh.md) · [`INSTALL.md`](../../INSTALL.md)
