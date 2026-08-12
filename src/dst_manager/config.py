from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """只接受显式路径，不通过注册表或 PATH 猜测 AutoCAD。"""

    data_dir: Path = Path(".dst-manager-data")
    autocad_2016_console: Path | None = None
    autocad_2016_plugin: Path | None = None
    autocad_2020_console: Path | None = None
    autocad_2020_plugin: Path | None = None
    cad_timeout_seconds: int = 600
    cad_max_parallel: int = Field(default=2, ge=1, le=4)
    worker_lease_seconds: int = Field(default=120, ge=30, le=3600)
    model_config = SettingsConfigDict(env_prefix="DST_MANAGER_", env_file=".env")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'dst-manager.db').resolve().as_posix()}"
