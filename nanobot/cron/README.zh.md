# nanobot/cron/

Nanobot 框架的定时 agent 任务（cron 服务）。

[English](README.md) · [中文]

## 用途

定义 cron 任务类型与可按计划跑绑定 agent 回合的 `CronService`。产品 RBP 评估 / evolve 循环使用 `rbp_eval` 与 cert shell 脚本；在启用时 cron 仍可用于框架级调度。

## 布局

| 模块 | 角色 |
|------|------|
| `types.py` | `CronJob`、`CronSchedule` |
| `service.py` | `CronService` |
| `bound_runner.py` | 定时回合的绑定 runner |
| `session_delivery.py` / `session_turns.py` | 会话投递辅助 |
| `webui_metadata.py` | 元数据辅助（遗留 WebUI） |

## 入口

```python
from nanobot.cron import CronService, CronJob, CronSchedule
```

## 代码示例

```python
from nanobot.cron import CronJob, CronSchedule
from nanobot.cron.types import CronPayload

schedule = CronSchedule(kind="cron", expr="0 * * * *")
job = CronJob(
    id="hourly-ping",
    name="hourly-ping",
    schedule=schedule,
    payload=CronPayload(message="ping"),
)
print(job.id, job.schedule.expr)
```

```bash
nanobot-bio evolve --dry-run
bash scripts/cert/smoke_evolve_loop.sh
```

## 依赖 / 环境

- 启动服务时需要 Nanobot runtime/config。
- chat / own-head / LOO 认证路径不依赖本包。

## 相关文档

[`../README.zh.md`](../README.zh.md) · [`../../rbp_eval/evolve/README.zh.md`](../../rbp_eval/evolve/README.zh.md)
