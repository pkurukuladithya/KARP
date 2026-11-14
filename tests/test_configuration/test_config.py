import os
import json
import tempfile
import unittest
from pathlib import Path
from shared.config.system_config import SystemConfig


class TestConfiguration(unittest.TestCase):
    def test_default_config_loading(self):
        config = SystemConfig()
        data = config.to_dict()
        self.assertIn("network", data)
        self.assertIn("video", data)
        self.assertIn("vision", data)
        self.assertIn("sensors", data)
        self.assertEqual(config.get("network", "video_port_pi_to_laptop"), 5000)
        self.assertEqual(config.get("vision", "confidence_threshold"), 0.45)

    def test_env_override(self):
        os.environ["KARP_LAPTOP_IP"] = "192.168.10.200"
        os.environ["KARP_CONFIDENCE_THRESHOLD"] = "0.75"
        try:
            config = SystemConfig()
            self.assertEqual(config.get("network", "laptop_ip"), "192.168.10.200")
            self.assertEqual(config.get("vision", "confidence_threshold"), 0.75)
        finally:
            del os.environ["KARP_LAPTOP_IP"]
            del os.environ["KARP_CONFIDENCE_THRESHOLD"]

    def test_config_set_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "test_user_cfg.json"
            config = SystemConfig(config_path=test_path)
            config.set("sensors", "vibration_threshold_g", 3.14, save_to_disk=True)

            self.assertTrue(test_path.exists())
            with open(test_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["sensors"]["vibration_threshold_g"], 3.14)

            # Reload with new instance
            reloaded = SystemConfig(config_path=test_path)
            self.assertEqual(reloaded.get("sensors", "vibration_threshold_g"), 3.14)


if __name__ == "__main__":
    unittest.main()
