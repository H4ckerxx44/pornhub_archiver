import os
from pathlib import Path

_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_ENV_VALUES


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _int_env("DB_PORT", 3306)
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = "ph_archiver"

DATA_PATH = Path(os.getenv("DATA_PATH", "/data"))
SLEEP_INTERVAL = _int_env("SLEEP_INTERVAL", 3600)
RUN_ONCE = _bool_env("RUN_ONCE", False)
OPENSSL_CONF = os.getenv("OPENSSL_CONF")
STEP_SLEEP_INTERVAL = _int_env("STEP_SLEEP_INTERVAL", 15)
CONCURRENT_FRAGMENT_DOWNLOADS = _int_env("CONCURRENT_FRAGMENT_DOWNLOADS", 4)

LOKI_URL = os.getenv("LOKI_URL", "").strip()
LOKI_USERNAME = os.getenv("LOKI_USERNAME", "").strip()
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD", "").strip()
LOKI_LABELS = os.getenv("LOKI_LABELS", "").strip()
LOKI_APP_LABEL = os.getenv("LOKI_APP_LABEL", "pornhub-archiver").strip()
LOKI_TIMEOUT = _float_env("LOKI_TIMEOUT", 5)
LOG_PATH = os.getenv("LOG_PATH", "/logs").strip()
CONSOLE_COLORS = _bool_env("CONSOLE_COLORS", True)


def current_log_path() -> str:
    return os.getenv("LOG_PATH", "/logs").strip()
