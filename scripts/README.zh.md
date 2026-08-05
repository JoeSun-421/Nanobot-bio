# scripts/

nanobot-bio 运维脚本。**日常入口：** [`nbio`](nbio)。

[English](README.md) · [中文]

## 功能



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

- **`nbio`**：可移植 activate / status / doctor / setup / chat / **start**（Linux 万能一键）
- Setup：agent `.venv` + delivery 科学 conda + AF3 栈选型
- CI / Cert / Docker / Data 辅助脚本（文件名未改）

## 路径发现（通用 Linux）

`nbio` / `setup_*` **按 checkout 与标准环境变量发现路径**，不含厂商机绝对路径：

| 目标 | 候选顺序（摘要） |
|------|------------------|
| `BIO_ROOT` / delivery | 相对 `scripts/nbio.sh` 的 checkout → `$BIO_ROOT` / `$DELIVERY_ROOT`（仅当目录仍存在） |
| `AF3_BLACKWELL_ROOT` | `$AF3_BLACKWELL_ROOT` → `$BIO_ROOT/af3_blackwell` → BIO 父目录旁 → `~/af3_blackwell` → `/opt/af3_blackwell` |
| `AF3_PYTHON` | `$ENV_PREFIX` → `conda info --base` → `$CONDA_PREFIX` / 常见 miniconda·anaconda → `$BIO_ROOT/../conda` 或 `$BIO_ROOT/conda` |

`./scripts/nbio.sh start`（或 `--dry-run`）会打印候选列表与选中项，并按本机结果 heal `.env`（先备份 `.env.bak.nbio.*`）。新机器：放好 delivery 与（可选）af3_blackwell 后执行 `nbio setup` → `nbio start`。

## 实现方法

| 路径 | 用途 |
|------|------|
| [`nbio`](nbio) | **用户唯一入口**（探测+激活；安装须显式 setup） |
| [`setup/`](setup/README.zh.md) | 重装（`setup_all*`）；`activate_env.sh` → `nbio`（兼容薄包装） |
| [`ci/`](ci/README.zh.md) | 密钥扫描与工程门禁 |
| [`cert/`](cert/README.zh.md) | 非 LLM 认证、清单、冒烟 |
| [`docker/`](docker/README.zh.md) | 容器入口 |
| [`data/`](data/README.zh.md) | delivery `agent_db` 幂等重建 |

```
scripts/
  nbio                 ← 日常入口（canonical）
  setup/               setup_all*；activate_env / ampere / blackwell = 兼容薄包装
  ci/ cert/ docker/ data/
```

## 怎么使用

```bash
git clone https://github.com/JoeSun-421/Nanobot-bio.git
cd Nanobot-bio
./scripts/nbio.sh setup                 # 首次
./scripts/nbio.sh start                 # 日常万能一键：本机路径发现 → 纠偏 AF3 → chat
# ./scripts/nbio.sh start --dry-run     # 只看候选列表与自动适配，不启动
# source scripts/nbio.sh && nanobot-bio chat   # 等价分步
```

`start` / `up` 会按 `compute_cap` 选择 classic / blackwell，纠偏 `AF3_DIR`·`AF3_PYTHON`·`AF3_CACHE`（默认 heal `.env` 并备份；`--no-heal` 仅会话生效）。安装说明见 [`INSTALL.md`](../INSTALL.md)。

## Delivery 桥

科学 I/O 走 App delivery 包（非本目录脚本）。简述见 [`../app/backends/delivery/README.zh.md`](../app/backends/delivery/README.zh.md) · [EN](../app/backends/delivery/README.md)。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`INSTALL.md`](../INSTALL.md) · [`nbio`](nbio)
