# scripts/docker/

nanobot-bio 镜像的容器运行时入口。

[English](README.md) · [中文]

## 功能

- 容器启动时轻量自检，再 `exec` 用户命令（默认 `nanobot-bio chat`）
- 存在 `DELIVERY_ROOT` 时 best-effort `apply_delivery_env`
- 交接 CMD 前做 overlay sync
- 科学数据与 LLM 配置经 volume / 环境变量挂入，不烤进镜像

## 实现方法

| 文件 | 作用 |
|------|------|
| `docker-entrypoint.sh` | 若存在 `DELIVERY_ROOT`（默认 `/delivery`）则 best-effort 应用 env；除非 `SKIP_DOCTOR=1` 否则跑 `python -m app doctor`（失败仅 WARN）；sync overlay；最后 `exec "$@"` |

由 [`Dockerfile`](../../Dockerfile) 接入：

```dockerfile
COPY scripts/docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["nanobot-bio", "chat"]
```

本地编排见根目录 `docker-compose.yml`。构建与挂载说明见 [`INSTALL.md`](../../INSTALL.md)「路径 B：Docker」。

## 怎么使用

```bash
docker build -t nanobot-bio:agent .
docker run --rm \
 -v $BIO_ROOT/rhobind_agent_delivery:/delivery \
 -e DELIVERY_ROOT=/delivery \
 -v $HOME/.nanobot:/root/.nanobot \
 nanobot-bio:agent doctor
```

| 变量 | 默认 / 说明 |
|------|-------------|
| `NANOBOT_BIO_ROOT` | `/bio/nanobot-bio` |
| `NANOBOT_WORKSPACE` | `$NANOBOT_BIO_ROOT/workspace` |
| `NANOBOT_CONFIG` | `/root/.nanobot/config.json` |
| `DELIVERY_ROOT` | `/delivery`（需挂载 sibling bundle） |
| `SKIP_DOCTOR` | `1` 跳过启动自检 |

## 设计思路

- entrypoint 对 doctor 软失败，科学挂载不完整时容器仍可用于 `layout` / 排障。
- 数据不进镜像层；协作方挂载 `agent_db` / AF3 参数 / 配置。
- 容器内外同一 CLI 面（`nanobot-bio …`）。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../Dockerfile`](../../Dockerfile)
