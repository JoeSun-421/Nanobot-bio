# app/core/

产品运行时辅助：路径、配置、能力探测、verdict JSON 与 chat UX。**本包不跑 agent loop，也不计算科学 `p_hat`。**

[English](README.md) · [中文]

## 用途

`app.core` 是 CLI、`RBPAgent`、delivery 桥与离线评估写盘共用的胶水层。它负责：规范 artifact 目录、deep-merge 运行时 YAML（`defaults.yaml` ± `evolved.yaml`）、AF3 / peaks / delivery 冒烟的诚实探测，以及把 LLM 文本规整为可信任 JSON verdict 的 normalize / validate 路径。

评估专用融合数学在 [`rbp_eval/`](../../rbp_eval/README.zh.md)。交互主路径是 [`app.agent.RBPAgent`](../agent.py) → Nanobot，而不是这里的固定 pipeline。

## 布局

| 模块 | 角色 |
|------|------|
| `paths.py` | 规范 `artifacts/{sessions,traces,reports,cache,…}`、报告路径、迁移 |
| `runtime_config.py` | `load_runtime_config()`、`fusion_weights()`、标签 / 弃权阈值 |
| `capability_matrix.py` | 探测 AF3 / peaks / delivery；为 `doctor` 写能力矩阵 |
| `verdict_schema.py` | `normalize_verdict`、`validate_verdict`、`extract_verdict_from_content` |
| `onboard.py` | 交互 / 非交互 LLM 提供商与密钥配置 |
| `chat_ux.py` | 安静日志、可见工具步骤、chat 中 verdict 展示 |
| `science_request.py` | 解析用户科学提问（RNA / RBP 提示） |
| `product_authority.py` | 能力诚实相关的产品权威说明 |
| `model_registry.py` | 模型 id 辅助 |
| `fusion_rna_policy.py` | peaks 未就绪时将 RNA-peak 融合权重置 0 |

## 入口 / 导入

```python
from app.core.paths import ARTIFACTS, ensure_artifact_dirs, report_path, DEFAULT_LOO_REPORT
from app.core.runtime_config import load_runtime_config, fusion_weights, label_thresholds
from app.core.verdict_schema import normalize_verdict, validate_verdict, extract_verdict_from_content
from app.core.capability_matrix import probe_capabilities, write_capability_matrix

# 懒加载再导出同样可用：
from app.core import normalize_verdict, validate_verdict
```

## 代码示例

**Artifact 与报告路径**

```python
from app.core.paths import ensure_artifact_dirs, report_path, find_report

dirs = ensure_artifact_dirs()  # 创建 artifacts/sessions, reports/json, …
out = report_path("eval_loo_report.json")  # → artifacts/reports/json/…
existing = find_report("eval_loo_report.json")
```

**运行时配置与融合权重**

```python
from app.core.runtime_config import load_runtime_config, fusion_weights, config_source

cfg = load_runtime_config(prefer_evolved=True)
print(config_source())          # 当前生效的 YAML 层
print(fusion_weights())         # rna_peak_homology 可能被强制为 0
```

**Verdict 规整 / 校验**

```python
from app.core.verdict_schema import extract_verdict_from_content, validate_verdict

raw = extract_verdict_from_content('{"label":"binds","p_hat":0.91,"confidence":"high"}')
ok, errors = validate_verdict(raw)
assert ok, errors
```

## 依赖 / 环境

- 读取 `config/defaults.yaml`，可选 `config/evolved.yaml`（需 `evolved: true`）。
- 能力探测可能触及 `DELIVERY_ROOT`、AF3 状态文件与 delivery 冒烟报告——见 [`INSTALL.md`](../../INSTALL.md)。
- 路径 / 配置 / verdict 辅助不需要 GPU；`probe_capabilities` 可能检查 conda 环境。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../docs/product/BINDING_PREDICTION_FLOW.zh.md`](../../docs/product/BINDING_PREDICTION_FLOW.zh.md) · [`../../config/README.zh.md`](../../config/README.zh.md) · [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)
