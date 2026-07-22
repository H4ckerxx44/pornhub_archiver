import importlib
import os
import unittest


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.old_env)
        import pornhub_archiver.config as config

        importlib.reload(config)

    def test_invalid_values_fall_back_and_record_warnings(self) -> None:
        os.environ["DB_PORT"] = "not-a-port"
        os.environ["RUN_ONCE"] = "maybe"
        os.environ["STEP_SLEEP_INTERVAL"] = "-1"
        os.environ["LOKI_TIMEOUT"] = "0"

        import pornhub_archiver.config as config

        config = importlib.reload(config)

        self.assertEqual(config.DB_PORT, 3306)
        self.assertFalse(config.RUN_ONCE)
        self.assertEqual(config.STEP_SLEEP_INTERVAL, 15)
        self.assertEqual(config.LOKI_TIMEOUT, 5)
        self.assertEqual(len(config.CONFIG_WARNINGS), 4)
        self.assertTrue(all("using default" in warning for warning in config.CONFIG_WARNINGS))

    def test_valid_values_do_not_record_warnings(self) -> None:
        os.environ["DB_PORT"] = "3307"
        os.environ["RUN_ONCE"] = "true"
        os.environ["STEP_SLEEP_INTERVAL"] = "0"
        os.environ["LOKI_TIMEOUT"] = "2.5"

        import pornhub_archiver.config as config

        config = importlib.reload(config)

        self.assertEqual(config.DB_PORT, 3307)
        self.assertTrue(config.RUN_ONCE)
        self.assertEqual(config.STEP_SLEEP_INTERVAL, 0)
        self.assertEqual(config.LOKI_TIMEOUT, 2.5)
        self.assertEqual(config.CONFIG_WARNINGS, [])


if __name__ == "__main__":
    unittest.main()
