import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


class _ArrowNow:
    def format(self, fmt: str) -> str:
        return "2026-01-02 03:04:05 +00:00"


class _ClientTimeout:
    def __init__(self, total: float) -> None:
        self.total = total


class _BasicAuth:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password


class _ClientError(Exception):
    pass


class _ClientSession:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def import_logger_module() -> types.ModuleType:
    sys.modules.pop("pornhub_archiver.logger", None)
    sys.modules["arrow"] = types.SimpleNamespace(utcnow=lambda: _ArrowNow())
    sys.modules["aiohttp"] = types.SimpleNamespace(
        BasicAuth=_BasicAuth,
        ClientError=_ClientError,
        ClientSession=_ClientSession,
        ClientTimeout=_ClientTimeout,
    )
    return importlib.import_module("pornhub_archiver.logger")


class LoggerHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_env = os.environ.copy()
        self.logger_module = import_logger_module()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_bool_env_accepts_truthy_values(self) -> None:
        for value in ("1", "true", "yes", "on", "TRUE"):
            with self.subTest(value=value):
                os.environ["FLAG"] = value
                self.assertTrue(self.logger_module._bool_env("FLAG", False))

        os.environ["FLAG"] = "false"
        self.assertFalse(self.logger_module._bool_env("FLAG", True))

    def test_float_env_falls_back_on_invalid_value(self) -> None:
        os.environ["NUMBER"] = "invalid"
        self.assertEqual(self.logger_module._float_env("NUMBER", 1.5), 1.5)

        os.environ["NUMBER"] = "2.25"
        self.assertEqual(self.logger_module._float_env("NUMBER", 1.5), 2.25)

    def test_loki_push_url_normalizes_base_url(self) -> None:
        self.assertEqual(self.logger_module.LokiClient._push_url(""), "")
        self.assertEqual(
            self.logger_module.LokiClient._push_url("http://loki:3100"),
            "http://loki:3100/loki/api/v1/push",
        )
        self.assertEqual(
            self.logger_module.LokiClient._push_url("http://loki:3100/loki/api/v1/push"),
            "http://loki:3100/loki/api/v1/push",
        )

    def test_labels_parse_extra_values(self) -> None:
        self.logger_module.LOKI_APP_LABEL = "app-name"
        self.logger_module.LOKI_LABELS = "env=prod, bad, region=eu "

        labels = self.logger_module.LokiClient._labels()

        self.assertEqual(labels["app"], "app-name")
        self.assertEqual(labels["env"], "prod")
        self.assertEqual(labels["region"], "eu")
        self.assertIn("host", labels)
        self.assertNotIn("bad", labels)

    def test_format_message_without_colors(self) -> None:
        message = self.logger_module.AsyncLogger.format_message("info", "hello", colors=False)

        self.assertEqual(message, "[2026-01-02 03:04:05 +00:00] [INFO   ] hello")

    def test_format_for_non_console_log_strips_leading_whitespace(self) -> None:
        self.assertEqual(
            self.logger_module.AsyncLogger._format_for_non_console_log("\t  message"),
            "message",
        )

    def test_file_log_sink_writes_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = self.logger_module.FileLogSink()
            sink.path = Path(tmp)
            sink.start()
            sink.write("info", "hello")

            self.assertIsNotNone(sink.file_path)
            self.assertIn("hello", sink.file_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
