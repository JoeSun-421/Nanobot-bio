# tests/

Pytest 套件：布局、契约、CLI/UX、delivery 桥与离线评估逻辑。

[English](README.md) · [中文]

## 功能



## 通用布局（Linux）

```bash
export BIO_ROOT="${BIO_ROOT:-$HOME/bio_agent}"
cd "$BIO_ROOT/nanobot-bio"
source scripts/nbio.sh
```

- 提案 / Table 合规与 slim-vendor 包布局断言
- 能力矩阵诚实性、soft-fail caveat、verdict / 阶段契约
- Chat UX、onboard、设备、会话日期布局、记忆/提升阶段检查
- mapping 与 delivery registry 同步；cert 脚本冒烟契约
- Marker：缺 delivery/GPU 时在公开 CI 干净 skip

## 实现方法

| 文件 / 模式 | 说明 |
|-------------|------|
| `conftest.py` | `requires_delivery` marker；无 `DELIVERY_ROOT` / 同级 bundle 时 skip |
| `test_package_layout.py` | 目录与 slim-vendor 断言 |
| `test_proposal_compliance.py` | Table 3 / skill / 配置合规 |
| `test_capability_matrix.py` / `test_softfail_caveats.py` | 能力诚实与 soft-fail |
| `test_*evolve*` / `test_run_eval.py` / `test_promote_evolved.py` | 演化与评估 |
| `test_smoke_delivery_tools.py` | 与 `scripts/cert/smoke_delivery_tools.py` 相关的契约 |
| 其它 `test_*.py` | chat UX、onboard、own-head、session 布局、mapping sync 等 |

`pyproject.toml`：`testpaths = ["tests"]`，覆盖 `app` + `rbp_eval`（`--cov-fail-under=33`），marker：`science` / `requires_delivery`。

## 怎么使用

```bash
source .venv/bin/activate
pytest -q
pytest tests/test_proposal_compliance.py tests/test_package_layout.py
bash scripts/ci/ci_gate.sh          # ruff + pytest + layout（app gate）
bash scripts/cert/certify.sh        # 含 pytest 的更长认证链
```

常用环境变量：`NANOBOT_BIO_ROOT`、可选 `DELIVERY_ROOT`、`RHOBIND_DEVICE`。

## 设计思路

- 公开 CI **没有** delivery/GPU：科学用例应 skip，而不是假绿。
- 不要为变绿删除 `requires_delivery`，或把 mock 分数当真值验收。
- 产物写在 `artifacts/`；测试不应依赖把密钥提交进仓库。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../scripts/ci/README.zh.md`](../scripts/ci/README.zh.md) · [`AGENTS.md`](../AGENTS.md)
