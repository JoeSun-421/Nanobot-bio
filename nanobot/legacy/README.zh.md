# nanobot/legacy/

隔离的非产品 Nanobot 子系统（遗留 apps / CLI）。

[English](README.md) · [中文]

## 用途

存放不属于 nanobot-bio 产品路径的旧 Nanobot app/CLI 表面。为框架连续性保持可导入；产品操作者应使用 `nanobot-bio` / `app.cli`。

## 布局

| 路径 | 角色 |
|------|------|
| `__init__.py` | 包标记 |
| [`apps/`](apps/README.zh.md) · [`apps/cli/`](apps/cli/README.zh.md) | 遗留 app/CLI 包 |

## 入口

推荐：

```bash
nanobot-bio --help
python -m app --help
```

## 代码示例

```python
import nanobot.legacy
print(nanobot.legacy.__doc__)
```

```bash
nanobot-bio layout
```

## 依赖 / 环境

- RBP chat / eval / certify 不依赖本包。
- 框架测试仍可能导入。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../app/cli/README.zh.md`](../../app/cli/README.zh.md)
