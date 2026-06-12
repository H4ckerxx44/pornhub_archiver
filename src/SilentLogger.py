import asyncio
import os
import socket
import time

import aiohttp
import arrow


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


LOKI_URL = os.getenv("LOKI_URL", "").strip()
LOKI_USERNAME = os.getenv("LOKI_USERNAME", "").strip()
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD", "").strip()
LOKI_LABELS = os.getenv("LOKI_LABELS", "").strip()
LOKI_APP_LABEL = os.getenv("LOKI_APP_LABEL", "pornhub-archiver").strip()
LOKI_TIMEOUT = _float_env("LOKI_TIMEOUT", 5)
CONSOLE_COLORS = _bool_env("CONSOLE_COLORS", True)

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_LEVEL_COLORS = {
    "debug": "\033[90m",
    "info": "\033[36m",
    "warning": "\033[33m",
    "error": "\033[31m",
}


class LokiClient:
    def __init__(self) -> None:
        self.url = self._push_url(LOKI_URL)
        self.labels = self._labels()
        self.timeout = LOKI_TIMEOUT
        self.session: aiohttp.ClientSession | None = None
        self._warning_printed = False
        self._not_started_warning_printed = False

    def enabled(self) -> bool:
        return bool(self.url)

    async def start(self) -> None:
        if not self.enabled() or self.session is not None:
            return

        auth = None
        if LOKI_USERNAME or LOKI_PASSWORD:
            auth = aiohttp.BasicAuth(LOKI_USERNAME, LOKI_PASSWORD)

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        headers = {"User-Agent": "pornhub-archiver"}
        self.session = aiohttp.ClientSession(timeout=timeout, headers=headers, auth=auth)

    async def close(self) -> None:
        if self.session is None:
            return

        await self.session.close()
        self.session = None

    async def send(self, level: str, msg: str) -> None:
        if not self.enabled():
            return

        if self.session is None:
            self.print_not_started_warning_once()
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

        try:
            async with self.session.post(self.url, json=payload) as response:
                if response.status >= 400:
                    text = await response.text()
                    self.print_warning_once(f"HTTP {response.status}: {text[:200]}")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            self.print_warning_once(exc)

    def print_not_started_warning_once(self) -> None:
        if self._not_started_warning_printed:
            return
        self._not_started_warning_printed = True
        print(
            SilentLogger.format_console_message("warning", "system - Loki logger was not started; dropping Loki messages"),
            flush=True,
        )

    def print_warning_once(self, exc: Exception | str) -> None:
        if self._warning_printed:
            return
        self._warning_printed = True
        msg = f"system - failed to send logs to Loki: {exc}"
        print(SilentLogger.format_console_message("warning", msg), flush=True)

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
    _pending_loki_tasks: set[asyncio.Task] = set()

    def __init__(self, send_to_console: bool = False) -> None:
        self.send_to_console = send_to_console

    @staticmethod
    async def start() -> None:
        await _loki.start()

    @staticmethod
    async def stop() -> None:
        if SilentLogger._pending_loki_tasks:
            await asyncio.gather(*SilentLogger._pending_loki_tasks, return_exceptions=True)
        await _loki.close()

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
            print(self.format_console_message(level, msg), flush=True)
        self._send_to_loki(level, msg)

    @staticmethod
    def format_console_message(level: str, msg: str) -> str:
        timestamp = arrow.utcnow().format("YYYY-MM-DD HH:mm:ss ZZ")
        level_name = level.upper().ljust(7)
        return SilentLogger.colorize(level, f"{timestamp} {level_name} {msg}")

    @staticmethod
    def colorize(level: str, msg: str) -> str:
        if not CONSOLE_COLORS:
            return msg

        color = _LEVEL_COLORS.get(level.lower())
        if not color:
            return msg

        if level.lower() in ("warning", "error"):
            return f"{_BOLD}{color}{msg}{_RESET}"

        if level.lower() == "debug":
            return f"{_DIM}{color}{msg}{_RESET}"

        return f"{color}{msg}{_RESET}"

    def _send_to_loki(self, level: str, msg: str) -> None:
        if not _loki.enabled():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _loki.print_not_started_warning_once()
            return

        task = loop.create_task(_loki.send(level, msg))
        SilentLogger._pending_loki_tasks.add(task)
        task.add_done_callback(self._consume_loki_task_exception)

    @staticmethod
    def _consume_loki_task_exception(task: asyncio.Task) -> None:
        SilentLogger._pending_loki_tasks.discard(task)
        try:
            task.result()
        except Exception as exc:
            _loki.print_warning_once(exc)


class AppLogger(SilentLogger):
    def __init__(self, send_to_console: bool) -> None:
        super().__init__(send_to_console=send_to_console)


_loki = LokiClient()
logger = AppLogger(send_to_console=True)
