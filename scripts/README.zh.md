# scripts/

nanobot-bio 运维脚本。**日常入口：** [`nbio`](nbio)。

[English](README.md) · [中文]

## 功能

- **`nbio`**：可移植 activate / status / doctor / setup / chat（Linux）
- Setup：agent `.venv` + delivery 科学 conda + AF3 栈选型
- CI / Cert / Docker / Data 辅助脚本（文件名未改）

## 实现方法

| 路径 | 用途 |
|------|------|
| [`nbio`](nbio) | **用户唯一入口**（探测+激活；安装须显式 setup） |
| [`setup/`](setup/README.zh.md) | 重装（`setup_all*`）；`activate_env.sh` → `nbio` |
| [`ci/`](ci/README.zh.md) | 密钥扫描与工程门禁 |
| [`cert/`](cert/README.zh.md) | 非 LLM 认证、清单、冒烟 |
| [`docker/`](docker/README.zh.md) | 容器入口 |
| [`data/`](data/README.zh.md) | delivery `agent_db` 幂等重建 |

```
scripts/
  nbio                 ← 日常入口
  setup/               setup_all*, activate_env.sh（兼容）
  ci/ cert/ docker/ data/
```

## 怎么使用

```bash
git clone https://github.com/JoeSun-421/Nanobot-bio.git
cd Nanobot-bio
./scripts/nbio setup
source scripts/nbio
nanobot-bio doctor
nanobot-bio chat
```

安装说明见 [`INSTALL.md`](../INSTALL.md)。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`INSTALL.md`](../INSTALL.md) · [`nbio`](nbio)
