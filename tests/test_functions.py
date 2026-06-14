import unittest
from datetime import UTC, datetime, timedelta

from pornhub_archiver.functions import format_si, nice_timedelta, spacer, video_url_from_id


class FunctionTests(unittest.TestCase):
    def test_video_url_from_id_builds_view_url(self) -> None:
        self.assertEqual(
            video_url_from_id("ph123"),
            "https://www.pornhub.org/view_video.php?viewkey=ph123",
        )

    def test_nice_timedelta_returns_difference(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = start + timedelta(seconds=90)

        self.assertEqual(nice_timedelta(end, start), timedelta(seconds=90))

    def test_format_si_formats_binary_units(self) -> None:
        cases = {
             0: "0 Bytes",
            1023: "1023 Bytes",
            1024: "1.00 KiB",
            1024 * 1024 * 2.5: "2.50 MiB",
        }

        for size, expected in cases.items():
            with self.subTest(size=size):
                self.assertEqual(format_si(size), expected)

    def test_spacer_uses_length_and_character(self) -> None:
        self.assertEqual(spacer(), "=" * 25)
        self.assertEqual(spacer(4, "-"), "----")


if __name__ == "__main__":
    unittest.main()
