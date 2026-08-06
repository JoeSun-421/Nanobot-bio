# scripts/setup/

面向 Linux / SSH 主机的**首次安装 / 修复**脚本。日常请用仓库根下的 [`../nbio.sh`](../nbio.sh)。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 功能

- 一次性（可重跑）配置 agent `.venv` + delivery 科学 conda + 可选 AF3 harden
- **import 级校验 + heal**：`rhobind`（torch+transformers）、`protein_embed`（transformers）、`rna`（mmseqs）、`af3`（可用 python）
- 按 GPU compute capability 自动选 AF3 栈（Blackwell CC 12.* vs 经典 `af3`）
- Ampere / Blackwell 薄包装入口

## 日常 vs 首次

| 场景 | 命令 |
|------|------|
| **日常** | `./scripts/nbio.sh start`（或 `source scripts/nbio.sh` → chat） |
| **首次 / 空壳修复** | `./scripts/nbio.sh setup`（或本目录 `setup_all.sh`） |
| 兼容旧激活 | `source scripts/setup/activate_env.sh` → 转发 `nbio activate`（薄包装，勿删） |

路径（`AF3_ROOT` / `ENV_PREFIX` / delivery）按本机发现，可用环境变量覆盖；见 [`../README.zh.md`](../README.zh.md)「路径发现」。

Delivery 切换与备份路径见 [delivery bridge](../../app/backends/delivery/README.zh.md)。

`nbio` **activate 不会**自动 `pip install` CUDA/torch；缺包时 doctor 表格标红，再用 `nbio setup` 修复。

## 实现方法

| 脚本 | 何时用 |
|------|--------|
| [`../nbio.sh`](../nbio.sh) | **用户入口（canonical）**：activate / status / doctor / setup / chat / start |
| `setup_all.sh` | `nbio setup` 内部调用；`AF3_STACK=auto`；AF3 路径可移植发现 |
| `setup_all_ampere_or_older.sh` | 薄包装（兼容）：强制 `AF3_STACK=classic` |
| `setup_all_blackwell.sh` | 薄包装（兼容）：强制 `AF3_STACK=blackwell` |
| `setup_af3_blackwell.sh` | **仅**安装/重装仓外 AF3；`AF3_ROOT` / `ENV_PREFIX` 可覆盖；默认按本机发现，非 AutoDL 专用 |
| `activate_env.sh` | 兼容包装 → `source ../nbio activate` |

## 怎么使用

```bash
./scripts/nbio.sh setup
./scripts/nbio.sh setup --skip-conda
bash scripts/setup/setup_all_blackwell.sh

./scripts/nbio.sh start # 日常：路径发现 → 纠偏 AF3 → chat
# source scripts/nbio.sh && nanobot-bio doctor
./scripts/nbio.sh status
```

完整说明见 [`INSTALL.md`](../../INSTALL.md)。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`INSTALL.md`](../../INSTALL.md) · [`../nbio.sh`](../nbio.sh)
