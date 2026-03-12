import unittest
from pathlib import Path

from quattrocento_demo.settings import SocketStreamSettings


class SocketSettingsTests(unittest.TestCase):
    def test_from_dict_accepts_valid_payload(self) -> None:
        settings = SocketStreamSettings.from_dict(
            {
                "host": "10.0.0.12",
                "port": 23000,
                "force_channel_indices": [0, 2, 4, 6, 8, 10, 12, 14, 16, 18],
                "aux_in_channel_index": 20,
                "decimation_enabled": False,
                "socket_read_size": 32768,
                "rec_on": True,
                "fsamp": 2048,
                "nch": 2,
                "conf2_defaults": {
                    "side": "left",
                    "hpf": 100,
                    "lpf": 900,
                    "mode": "bipolar",
                },
                "conf2_overrides": {
                    "IN1": {"mode": "differential"},
                },
            }
        )

        self.assertEqual(settings.host, "10.0.0.12")
        self.assertEqual(settings.port, 23000)
        self.assertEqual(settings.force_channel_indices, (0, 2, 4, 6, 8, 10, 12, 14, 16, 18))
        self.assertEqual(settings.aux_in_channel_index, 20)
        self.assertFalse(settings.decimation_enabled)
        self.assertEqual(settings.socket_read_size, 32768)
        self.assertTrue(settings.rec_on)
        self.assertEqual(settings.fsamp, 2048)
        self.assertEqual(settings.nch, 2)
        self.assertEqual(settings.input_conf2_bytes[0], 0b01101001)
        self.assertEqual(settings.input_conf2_bytes[1], 0b01101010)

    def test_from_dict_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValueError):
            SocketStreamSettings.from_dict({"unexpected": 1})

    def test_from_dict_rejects_non_boolean_rec_on(self) -> None:
        with self.assertRaises(ValueError):
            SocketStreamSettings.from_dict({"rec_on": "false"})

    def test_load_socket_settings_reads_toml_file(self) -> None:
        config_path = Path("tests") / "_tmp_socket_valid.toml"
        try:
            config_path.write_text(
                (
                    'host = "192.168.0.10"\n'
                    "port = 23456\n"
                    "fsamp = 512\n"
                    "nch = 3\n"
                    "force_channel_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]\n"
                    "aux_in_channel_index = 10\n"
                ),
                encoding="utf-8",
            )

            settings = SocketStreamSettings.from_toml_file(config_path)
            self.assertEqual(settings.host, "192.168.0.10")
            self.assertEqual(settings.port, 23456)
            self.assertEqual(settings.force_channel_indices, tuple(range(10)))
        finally:
            if config_path.exists():
                config_path.unlink()

    def test_load_socket_settings_rejects_invalid_file(self) -> None:
        config_path = Path("tests") / "_tmp_socket_invalid.toml"
        try:
            config_path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                SocketStreamSettings.from_toml_file(config_path)
        finally:
            if config_path.exists():
                config_path.unlink()


if __name__ == "__main__":
    unittest.main()
