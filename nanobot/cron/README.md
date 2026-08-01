# nanobot/cron/

Scheduled agent tasks (cron service) for the Nanobot framework.

[English] · [中文](README.zh.md)

## Purpose

Defines cron job types and a `CronService` that can run bound agent turns on a schedule. Product RBP evaluation / evolve loops use `rbp_eval` and shell cert scripts instead; cron remains available for framework-level scheduling when enabled.

## Layout

| Module | Role |
|--------|------|
| `types.py` | `CronJob`, `CronSchedule` |
| `service.py` | `CronService` |
| `bound_runner.py` | Bound runner for scheduled turns |
| `session_delivery.py` / `session_turns.py` | Session delivery helpers |
| `webui_metadata.py` | Metadata helper (legacy WebUI) |

## Entry points

```python
from nanobot.cron import CronService, CronJob, CronSchedule
```

## Code examples

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
# Product offline loops (preferred for science):
nanobot-bio evolve --dry-run
bash scripts/cert/smoke_evolve_loop.sh
```

## Dependencies / env

- Needs a running Nanobot runtime/config when the service is started.
- Not required for chat / own-head / LOO certification paths.

## See also

[`../README.md`](../README.md) · [`../../rbp_eval/evolve/README.md`](../../rbp_eval/evolve/README.md)
