import asyncio
import os
import socket
import time
from datetime import datetime, UTC

import aiohttp


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

    async def send(self, level: str, msg: str) -> None:
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

        auth = None
        if LOKI_USERNAME or LOKI_PASSWORD:
            auth = aiohttp.BasicAuth(LOKI_USERNAME, LOKI_PASSWORD)

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {"User-Agent": "pornhub-archiver"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers, auth=auth) as session:
                async with session.post(self.url, json=payload) as response:
                    if response.status >= 400:
                        text = await response.text()
                        self._print_warning_once(f"HTTP {response.status}: {text[:200]}")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            self._print_warning_once(exc)

    def _print_warning_once(self, exc: Exception | str) -> None:
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
        self._send_to_loki(level, msg)

    @staticmethod
    def _send_to_loki(level: str, msg: str) -> None:
        if not _loki.enabled():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_loki.send(level, msg))
            return

        task = loop.create_task(_loki.send(level, msg))
        task.add_done_callback(SilentLogger._consume_loki_task_exception)

    @staticmethod
    def _consume_loki_task_exception(task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception as exc:
            _loki._print_warning_once(exc)


class AppLogger(SilentLogger):
    def __init__(self, send_to_console: bool) -> None:
        super().__init__(send_to_console=send_to_console)


_loki = LokiClient()
logger = AppLogger(send_to_console=True)
