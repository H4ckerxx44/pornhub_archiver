import base64
import json
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, UTC


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


LOKI_URL = os.getenv("LOKI_URL", "").strip()
LOKI_USERNAME = os.getenv("LOKI_USERNAME", "").strip()
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD", "").strip()
LOKI_LABELS = os.getenv("LOKI_LABELS", "").strip()
LOKI_APP_LABEL = os.getenv("LOKI_APP_LABEL", "pornhub-archiver").strip()
LOKI_TIMEOUT = _float_env("LOKI_TIMEOUT", 5)


class LokiClient:
    def __init__(self) -> None:
        self.url = self._push_url(LOKI_URL)
        self.labels = self._labels()
        self.timeout = LOKI_TIMEOUT
        self._warning_printed = False

    def enabled(self) -> bool:
        return bool(self.url)

    def send(self, level: str, msg: str) -> None:
        if not self.enabled():
            return

        labels = self.labels | {"level": level.lower()}
        payload = {
            "streams": [
                {
                    "stream": labels,
                    "values": [[str(time.time_ns()), msg]],
                }
            ]
        }

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pornhub-archiver",
            },
            method="POST",
        )

        if LOKI_USERNAME or LOKI_PASSWORD:
            credentials = f"{LOKI_USERNAME}:{LOKI_PASSWORD}".encode("utf-8")
            token = base64.b64encode(credentials).decode("ascii")
            request.add_header("Authorization", f"Basic {token}")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                pass
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._print_warning_once(exc)

    def _print_warning_once(self, exc: Exception) -> None:
        if self._warning_printed:
            return
        self._warning_printed = True
        timestamp = datetime.now(UTC).isoformat()
        print(f"{timestamp} system - failed to send logs to Loki: {exc}", flush=True)

    @staticmethod
    def _push_url(url: str) -> str:
        if not url:
            return ""
        normalized = url.rstrip("/")
        return normalized if normalized.endswith("/loki/api/v1/push") else f"{normalized}/loki/api/v1/push"

    @staticmethod
    def _labels() -> dict[str, str]:
        labels = {
            "app": LOKI_APP_LABEL or "pornhub-archiver",
            "host": socket.gethostname(),
        }

        if not LOKI_LABELS:
            return labels

        for pair in LOKI_LABELS.split(","):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                labels[key] = value

        return labels


class SilentLogger:
    def __init__(self, send_to_console: bool = False) -> None:
        self.send_to_console = send_to_console

    def debug(self, msg: str) -> None:
        self._log("debug", msg)

    def info(self, msg: str) -> None:
        self._log("info", msg)

    def warning(self, msg: str) -> None:
        self._log("warning", msg)

    def error(self, msg: str) -> None:
        self._log("error", msg)

    def _log(self, level: str, msg: str) -> None:
        msg = str(msg)
        if self.send_to_console:
            print(msg, flush=True)
        _loki.send(level, msg)


class AppLogger(SilentLogger):
    def __init__(self, send_to_console: bool) -> None:
        super().__init__(send_to_console=send_to_console)


_loki = LokiClient()
logger = AppLogger(send_to_console=True)
