import asyncio
import os
import pathlib
import socket
import time
from collections.abc import Mapping

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


LOKI_URL: str = os.getenv("LOKI_URL", "").strip()
LOKI_USERNAME: str = os.getenv("LOKI_USERNAME", "").strip()
LOKI_PASSWORD: str = os.getenv("LOKI_PASSWORD", "").strip()
LOKI_LABELS: str = os.getenv("LOKI_LABELS", "").strip()
LOKI_APP_LABEL: str = os.getenv("LOKI_APP_LABEL", "pornhub-archiver").strip()
LOKI_TIMEOUT: float = _float_env("LOKI_TIMEOUT", 5)
LOG_PATH: str = os.getenv("LOG_PATH", "/logs").strip()
CONSOLE_COLORS: bool = _bool_env("CONSOLE_COLORS", True)

_RESET: str = "\033[0m"
_BOLD: str = "\033[1m"
_DIM: str = "\033[2m"
_LEVEL_COLORS: Mapping[str, str] = {
    "debug": "\033[90m",
    "info": "\033[36m",
    "warning": "\033[33m",
    "error": "\033[31m",
}


class LokiClient:
    def __init__(self) -> None:
        self.url: str = self._push_url(LOKI_URL)
        self.labels: dict[str, str] = self._labels()
        self.timeout: float = LOKI_TIMEOUT
        self.session: aiohttp.ClientSession | None = None

    def enabled(self) -> bool:
        return bool(self.url)

    async def start(self) -> None:
        if not self.enabled() or self.session is not None:
            return

        auth: aiohttp.BasicAuth | None = None
        if LOKI_USERNAME and LOKI_PASSWORD:
            auth = aiohttp.BasicAuth(LOKI_USERNAME, LOKI_PASSWORD)

        timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=self.timeout)
        headers: dict[str, str] = {"User-Agent": "pornhub-archiver"}
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
            self.print_not_started_warning()
            return

        labels: dict[str, str] = self.labels | {"level": level.lower()}
        payload: dict[str, list[dict[str, object]]] = {
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
                    self.print_warning(f"HTTP {response.status}: {text[:200]}")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            self.print_warning(exc)

    @staticmethod
    def print_not_started_warning() -> None:
        print(
            SilentLogger.format_console_message("warning", "system - Loki logger was not started; dropping Loki messages"),
            flush=True,
        )

    @staticmethod
    def print_warning(exc: Exception | str) -> None:
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
        labels: dict[str, str] = {
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
    _pending_loki_tasks: set[asyncio.Task[None]] = set()

    def __init__(
            self,
            send_to_console: bool = False,
            send_to_file: bool = True,
            send_to_loki: bool = True,
    ) -> None:
        self.send_to_console: bool = send_to_console
        self.send_to_file: bool = send_to_file
        self.send_to_loki: bool = send_to_loki

    @staticmethod
    async def start() -> None:
        _file_log_sink.start()
        await _loki.start()

    @staticmethod
    async def stop() -> None:
        if SilentLogger._pending_loki_tasks:
            await asyncio.gather(*SilentLogger._pending_loki_tasks, return_exceptions=True)
        await _loki.close()
        _file_log_sink.close()

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
        if self.send_to_file:
            _file_log_sink.write(level, self._format_for_non_console_log(msg))
        if self.send_to_loki:
            self._send_to_loki(level, self._format_for_non_console_log(msg))

    @staticmethod
    def format_console_message(level: str, msg: str) -> str:
        return SilentLogger.format_message(level, msg, colors=CONSOLE_COLORS)

    @staticmethod
    def format_message(level: str, msg: str, colors: bool) -> str:
        timestamp = arrow.utcnow().format("YYYY-MM-DD HH:mm:ss ZZ")
        level_name = level.upper().ljust(7)
        formatted = f"[{timestamp}] [{level_name}] {msg}"
        return SilentLogger.colorize(level, formatted) if colors else formatted

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

    @staticmethod
    def _format_for_non_console_log(msg: str) -> str:
        return msg.lstrip(" \t")

    def _send_to_loki(self, level: str, msg: str) -> None:
        if not _loki.enabled():
            return

        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            _loki.print_not_started_warning()
            return

        task: asyncio.Task[None] = loop.create_task(_loki.send(level, msg))
        SilentLogger._pending_loki_tasks.add(task)
        task.add_done_callback(self._consume_loki_task_exception)

    @staticmethod
    def _consume_loki_task_exception(task: asyncio.Task[None]) -> None:
        SilentLogger._pending_loki_tasks.discard(task)
        try:
            task.result()
        except Exception as exc:
            _loki.print_warning(exc)


class FileLogSink:
    def __init__(self) -> None:
        self.path: pathlib.Path | None = pathlib.Path(LOG_PATH) if LOG_PATH else None
        self.file_path: pathlib.Path | None = None
        self._warning_printed: bool = False

    def enabled(self) -> bool:
        return self.path is not None

    def start(self) -> None:
        if not self.enabled() or self.file_path is not None:
            return

        self.file_path = self._new_file_path()
        if self.file_path is None:
            return

        self._create_file()

    def _new_file_path(self) -> pathlib.Path | None:
        if self.path is None:
            return None

        try:
            self.path.mkdir(parents=True, exist_ok=True)
            return self.path / arrow.utcnow().format("YYYY-MM-DD HH:mm:ss")
        except OSError as exc:
            self.print_warning_once(exc)
            return None

    def _create_file(self) -> None:
        if self.file_path is None:
            return

        try:
            with self.file_path.open("a", encoding="utf-8"):
                pass
        except OSError as exc:
            self.file_path = None
            self.print_warning_once(exc)

    def close(self) -> None:
        self.file_path = None

    def write(self, level: str, msg: str) -> None:
        if not self.enabled() or self.file_path is None:
            return

        try:
            with self.file_path.open("a", encoding="utf-8") as file:
                print(SilentLogger.format_message(level, msg, colors=False), file=file, flush=True)
        except OSError as exc:
            self.print_warning_once(exc)

    def print_warning_once(self, exc: Exception | str) -> None:
        if self._warning_printed:
            return
        self._warning_printed = True
        msg = f"system - failed to write local log file: {exc}"
        print(SilentLogger.format_console_message("warning", msg), flush=True)


class AppLogger(SilentLogger):
    def __init__(self, send_to_console: bool) -> None:
        super().__init__(send_to_console=send_to_console, send_to_file=True, send_to_loki=True)


_file_log_sink: FileLogSink = FileLogSink()
_loki: LokiClient = LokiClient()
logger: AppLogger = AppLogger(send_to_console=True)
