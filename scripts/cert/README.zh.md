# scripts/cert/

非 LLM 认证路径、环境清单与 delivery / evolve 冒烟。

[English](README.md) · [中文]

> 包地图与 `$BIO_ROOT` 布局见仓库根 [`README.zh.md`](../../README.zh.md)。激活：`cd "${NANOBOT_BIO_ROOT:-$BIO_ROOT/Nanobot-bio}" && source scripts/nbio.sh`。

## 功能

- 可复现的交付前认证链，**从不读取或打印** LLM API key
- 环境与不可变输入哈希清单
- Delivery 工具冒烟（默认离线安全子集；可选 network / AF3）
- 自演化 → candidate → promote 干跑冒烟（临时夹具）

## 实现方法

| 文件 | 作用 |
|------|------|
| `certify.sh` | 编排认证路径；选项 `--network` / `--transfer` / `--release-metrics` / `--full` |
| `environment_manifest.py` | 写出 → `artifacts/reports/json/environment_manifest.json` |
| `smoke_delivery_tools.py` | 按 registry / mapping 冒烟；`--network` / `--af3` / `--report` |
| `smoke_evolve_loop.sh` | self-evolution → candidate → promote 干跑（不依赖真实长时 eval） |

`certify.sh` 流程（概念）：

```
certify.sh
 ├─ environment_manifest.py
 ├─ python -m app doctor
 ├─ python -m rbp_eval.accept.own_head
 ├─ smoke_delivery_tools.py
 ├─ （可选）release_metrics / transfer_calibration
 └─ pytest
```

仓库根：`$SCRIPT_DIR/../..`。优先用 `$ROOT/.venv/bin/python`。

## 怎么使用

```bash
bash scripts/cert/certify.sh
bash scripts/cert/certify.sh --full
bash scripts/cert/certify.sh --transfer # 可选 CERTIFY_TARGET / CERTIFY_MAX_SEQS

python scripts/cert/environment_manifest.py
python scripts/cert/smoke_delivery_tools.py
python scripts/cert/smoke_delivery_tools.py --network --af3

bash scripts/cert/smoke_evolve_loop.sh
```

Transfer 校准亦可 `python -m rbp_eval.accept.transfer_calibration`（见根 README）。

## 设计思路

- 协作方需要**不读密钥**的科学栈健康验收路径。
- 默认冒烟保持离线安全；network / AF3 可选，避免公开 CI 抖动。
- Evolve 冒烟用夹具，验证 promote 接线而无需数小时 LOO。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../rbp_eval/README.zh.md`](../../rbp_eval/README.zh.md) · [`INSTALL.md`](../../INSTALL.md)
