"""
System Resource & Performance Monitor.
Tracks CPU load, memory utilization, and network frame latency on the Raspberry Pi 4.
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class SystemMetrics:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    temperature_c: float = 0.0
    uptime_sec: float = 0.0


class PerformanceTracker:
    def __init__(self):
        self._start_time = time.time()

    def get_metrics(self) -> SystemMetrics:
        uptime = time.time() - self._start_time
        cpu_pct = 0.0
        mem_pct = 0.0
        temp_c = 0.0

        # Try psutil if available, otherwise read /proc or fallback safely
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
            mem_pct = psutil.virtual_memory().percent
        except ImportError:
            pass

        # Try reading Raspberry Pi thermal zone
        thermal_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_path):
            try:
                with open(thermal_path, "r") as f:
                    temp_c = float(f.read().strip()) / 1000.0
            except Exception:
                pass

        return SystemMetrics(
            cpu_percent=cpu_pct,
            memory_percent=mem_pct,
            temperature_c=temp_c,
            uptime_sec=uptime,
        )
