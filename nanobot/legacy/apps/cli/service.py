"""slim vendor stub for the CLI Apps service."""

from dataclasses import dataclass
from pathlib import Path


class CliAppError(ValueError):
    """User-facing CLI Apps failure."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(slots=True)
class CliAppsRuntimeConfig:
    install_timeout: int = 300
    run_timeout: int = 60
    catalog_ttl_seconds: int = 3600


class CliAppManager:
    """Disabled CLI Apps catalog and runner."""

    def __init__(
        self,
        workspace: Path | str | None = None,
        runtime: CliAppsRuntimeConfig | None = None,
    ) -> None:
        self.workspace = Path(workspace) if workspace is not None else Path.cwd()
        self.runtime = runtime or CliAppsRuntimeConfig()

    def installed_names(self) -> list[str]:
        return []

    def mentioned_installed_apps(self, text: str) -> list[dict[str, str]]:
        return []
