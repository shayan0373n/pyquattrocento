import unittest

from quattrocento.config import QuattrocentoConfig


class QuattrocentoConfigTests(unittest.TestCase):
    def test_default_mapping_uses_one_sensor_per_finger(self) -> None:
        config = QuattrocentoConfig()

        self.assertEqual(len(config.finger_sensor_map), 10)
        assigned = list(config.finger_sensor_map.values())
        self.assertEqual(sorted(assigned), list(range(10)))

    def test_duplicate_sensor_assignment_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            QuattrocentoConfig(
                finger_sensor_map={
                    "F1": 0,
                    "F2": 0,
                    "F3": 2,
                    "F4": 3,
                    "F5": 4,
                    "F6": 5,
                    "F7": 6,
                    "F8": 7,
                    "F9": 8,
                    "F10": 9,
                }
            )


if __name__ == "__main__":
    unittest.main()
