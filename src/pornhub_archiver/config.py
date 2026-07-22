import math
import os
from pathlib import Path

_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSY_ENV_VALUES = {"0", "false", "no", "off"}
CONFIG_WARNINGS: list[str] = []


def _warn_fallback(name: str, value: str, default: object, reason: str) -> None:
    CONFIG_WARNINGS.append(
        f"{name}={value!r} is invalid ({reason}); using default {default!r}"
    )


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUTHY_ENV_VALUES:
        return True
    if normalized in _FALSY_ENV_VALUES:
        return False
    _warn_fallback(name, value, default, "expected a boolean")
    return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        _warn_fallback(name, value, default, "expected a number")
        return default
    if not math.isfinite(parsed) or parsed <= 0:
        _warn_fallback(name, value, default, "expected a finite number greater than zero")
        return default
    return parsed


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        _warn_fallback(name, value, default, "expected an integer")
        return default


def _non_negative_int_env(name: str, default: int) -> int:
    value = _int_env(name, default)
    if value < 0:
        raw_value = os.getenv(name, str(value))
        _warn_fallback(name, raw_value, default, "expected a non-negative integer")
        return default
    return value


def _positive_int_env(name: str, default: int) -> int:
    value = _int_env(name, default)
    if value < 1:
        raw_value = os.getenv(name, str(value))
        _warn_fallback(name, raw_value, default, "expected a positive integer")
        return default
    return value


def _port_env(name: str, default: int) -> int:
    value = _positive_int_env(name, default)
    if value > 65535:
        raw_value = os.getenv(name, str(value))
        _warn_fallback(name, raw_value, default, "expected a port from 1 to 65535")
        return default
    return value


DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _port_env("DB_PORT", 3306)
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = "ph_archiver"

DATA_PATH = Path(os.getenv("DATA_PATH", "/data"))
SLEEP_INTERVAL = _non_negative_int_env("SLEEP_INTERVAL", 3600)
RUN_ONCE = _bool_env("RUN_ONCE", False)
OPENSSL_CONF = os.getenv("OPENSSL_CONF")
STEP_SLEEP_INTERVAL = _non_negative_int_env("STEP_SLEEP_INTERVAL", 15)
CONCURRENT_FRAGMENT_DOWNLOADS = _positive_int_env("CONCURRENT_FRAGMENT_DOWNLOADS", 4)

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
