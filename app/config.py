from __future__ import annotations
import os
from dataclasses import dataclass


def _load_dotenv() -> None:
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and os.getenv(key) is None:
                os.environ[key] = val


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "glpidb")
    db_user: str = os.getenv("DB_USER", "")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_connect_timeout: int = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
    sql_dir: str = os.getenv("SQL_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "SQL")))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL", "55"))
    cache_maxsize: int = int(os.getenv("CACHE_MAXSIZE", "128"))
    ssh_host: str = os.getenv("SSH_HOST", "")
    ssh_port: int = int(os.getenv("SSH_PORT", "32522"))
    ssh_user: str = os.getenv("SSH_USER", "")
    ssh_password: str = os.getenv("SSH_PASSWORD", "")
    ssh_strict: bool = os.getenv("SSH_STRICT", "0") in {"1", "true", "True"}
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
