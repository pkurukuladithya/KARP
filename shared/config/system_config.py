"""
Centralized Configuration Manager for KARP ADAS.
Supports defaults, JSON persistence, runtime updates, and environment overrides.
"""

from __future__ import annotations
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("KARP.Config")

DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.json"
USER_CONFIG_PATH = Path(__file__).parents[2] / "karp_user_config.json"


class SystemConfig:
    _instance: Optional[SystemConfig] = None
    _lock = threading.Lock()

    def __init__(self, config_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._user_path = config_path or USER_CONFIG_PATH
        self._data: Dict[str, Any] = {}
        # Only values explicitly persisted by the user (GUI). Never contains CLI/env overrides.
        self._user_data: Dict[str, Any] = {}
        self.load()

    @classmethod
    def get_instance(cls, config_path: Optional[Path] = None) -> SystemConfig:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config_path)
            return cls._instance

    def load(self) -> None:
        """Loads configuration from default, then overlays user config and env vars."""
        with self._lock:
            # 1. Load default config
            if DEFAULT_CONFIG_PATH.exists():
                try:
                    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load default config {DEFAULT_CONFIG_PATH}: {e}")
                    self._data = {}
            else:
                self._data = {}

            # 2. Read .env file if present in project root, then env var overrides
            self._load_dotenv_file()
            self._apply_env_overrides()

            # 3. Overlay persisted user config last (settings saved from the GUI win)
            self._user_data = {}
            if self._user_path.exists():
                try:
                    with open(self._user_path, "r", encoding="utf-8") as f:
                        user_data = json.load(f)
                    if isinstance(user_data, dict):
                        self._user_data = user_data
                        self._deep_update(self._data, user_data)
                except Exception as e:
                    logger.warning(f"Failed to load user config {self._user_path}: {e}")

    def _load_dotenv_file(self) -> None:
        """Reads .env file from project root and loads variables into os.environ."""
        env_path = Path(__file__).parents[2] / ".env"
        if not env_path.exists():
            return
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception as e:
            logger.warning(f"Failed to parse .env file at {env_path}: {e}")

    def _apply_env_overrides(self) -> None:
        env_map = {
            "KARP_LAPTOP_IP": ("network", "laptop_ip", str),
            "KARP_PI_IP": ("network", "pi_ip", str),
            "KARP_VIDEO_PORT_PI_TO_LAPTOP": ("network", "video_port_pi_to_laptop", int),
            "KARP_VIDEO_PORT_LAPTOP_TO_PI": ("network", "video_port_laptop_to_pi", int),
            "KARP_METADATA_WS_PORT": ("network", "metadata_ws_port", int),
            "KARP_CAMERA_INDEX": ("video", "camera_index", int),
            "KARP_VIDEO_WIDTH": ("video", "width", int),
            "KARP_VIDEO_HEIGHT": ("video", "height", int),
            "KARP_VIDEO_FPS": ("video", "fps", int),
            "KARP_STREAM_WIDTH": ("video", "stream_width", int),
            "KARP_STREAM_HEIGHT": ("video", "stream_height", int),
            "KARP_JPEG_QUALITY": ("video", "jpeg_quality", int),
            "KARP_RETURN_WIDTH": ("video", "return_width", int),
            "KARP_CAMERA_PASSTHROUGH": ("video", "camera_passthrough", lambda v: v.lower() in ("true", "1", "yes")),
            "KARP_CONFIDENCE_THRESHOLD": ("vision", "confidence_threshold", float),
            "KARP_IOU_THRESHOLD": ("vision", "iou_threshold", float),
            "KARP_YOLO_MODEL": ("vision", "model", str),
            "KARP_USE_CUDA": ("vision", "use_cuda", lambda v: v.lower() in ("true", "1", "yes")),
            "KARP_ESP32_PORT": ("sensors", "esp32_port", str),
            "KARP_ESP32_BAUDRATE": ("sensors", "baud_rate", int),
            "KARP_VIBRATION_THRESHOLD": ("sensors", "vibration_threshold_g", float),
            "KARP_SIMULATION_MODE": ("sensors", "simulation_mode", lambda v: v.lower() in ("true", "1", "yes")),
        }
        for env_key, (section, key, converter) in env_map.items():
            val = os.getenv(env_key)
            if val is not None:
                try:
                    if section not in self._data:
                        self._data[section] = {}
                    self._data[section][key] = converter(val)
                except Exception as e:
                    logger.warning(f"Invalid env override for {env_key}={val}: {e}")

    def _deep_update(self, base: Dict[str, Any], update: Dict[str, Any]) -> None:
        for k, v in update.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def get(self, section: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any, save_to_disk: bool = False) -> None:
        with self._lock:
            if section not in self._data:
                self._data[section] = {}
            self._data[section][key] = value
            if save_to_disk:
                self._user_data.setdefault(section, {})[key] = value

        if save_to_disk:
            self.save()

    def update_section(self, section: str, values: Dict[str, Any], save_to_disk: bool = False) -> None:
        with self._lock:
            if section not in self._data:
                self._data[section] = {}
            self._data[section].update(values)
            if save_to_disk:
                self._user_data.setdefault(section, {}).update(values)

        if save_to_disk:
            self.save()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def save(self, target_path: Optional[Path] = None) -> bool:
        """Persists user configuration to file using atomic write."""
        path = target_path or self._user_path
        tmp_path = path.with_suffix(".tmp")
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    # target_path given = explicit full export; default = user overrides only
                    json.dump(self._data if target_path else self._user_data, f, indent=2)
                tmp_path.replace(path)
                logger.info(f"Configuration saved to {path}")
                return True
            except Exception as e:
                logger.error(f"Failed to save configuration to {path}: {e}")
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                return False


def get_config() -> SystemConfig:
    return SystemConfig.get_instance()
