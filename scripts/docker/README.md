# scripts/docker/

Container runtime entrypoint for the nanobot-bio image.

[English] · [中文](README.zh.md)

## Features

- Light self-check on container start, then `exec` the user command (default `nanobot-bio chat`)
- Best-effort `apply_delivery_env` when `DELIVERY_ROOT` is present
- Overlay sync before handing off to the CMD
- Science data and LLM config enter via volumes / env — not baked into the image

## Implementation

| File | Role |
|------|------|
| `docker-entrypoint.sh` | If `DELIVERY_ROOT` (default `/delivery`) exists, best-effort env apply; unless `SKIP_DOCTOR=1`, run `python -m app doctor` (WARN on failure); sync overlay; `exec "$@"` |

Wired from [`Dockerfile`](../../Dockerfile):

```dockerfile
COPY scripts/docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["nanobot-bio", "chat"]
```

Local compose: root `docker-compose.yml`. Build/mount notes: [`INSTALL.md`](../../INSTALL.md) path B (Docker).

## How to use

```bash
docker build -t nanobot-bio:agent .
docker run --rm \
  -v $BIO_ROOT/rhobind_agent_delivery:/delivery \
  -e DELIVERY_ROOT=/delivery \
  -v $HOME/.nanobot:/root/.nanobot \
  nanobot-bio:agent doctor
```

| Variable | Default / notes |
|----------|-----------------|
| `NANOBOT_BIO_ROOT` | `/bio/nanobot-bio` |
| `NANOBOT_WORKSPACE` | `$NANOBOT_BIO_ROOT/workspace` |
| `NANOBOT_CONFIG` | `/root/.nanobot/config.json` |
| `DELIVERY_ROOT` | `/delivery` (mount sibling bundle) |
| `SKIP_DOCTOR` | `1` skips startup doctor |

## Design rationale

- Fail soft on doctor in entrypoint so containers remain usable for `layout` / debugging when science mounts are incomplete.
- Keep data out of the image layers; collaborators mount `agent_db` / AF3 params / config.
- Same CLI surface inside and outside Docker (`nanobot-bio …`).

## See also

[`../README.md`](../README.md) · [`INSTALL.md`](../../INSTALL.md) · [`../../Dockerfile`](../../Dockerfile)
