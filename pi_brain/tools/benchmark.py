"""
Measure what THIS machine can do (run it on the Pi after setup):

    python tools/benchmark.py            # detector backends + lane detector
    python tools/benchmark.py --threads 4
"""

from __future__ import annotations
import argparse
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from brain.camera import synthetic_road  # noqa: E402
from brain.config import load_config  # noqa: E402
from brain.detector import YoloDetector, available_backends  # noqa: E402
from brain.lanes import LaneDetector  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--runs", type=int, default=20)
    args = ap.parse_args()
    cfg = load_config()
    if args.threads:
        cfg["detector"]["threads"] = args.threads
    cv2.setNumThreads(1)

    print(f"Machine: {platform.machine()} / {platform.system()} / Python {platform.python_version()} / OpenCV {cv2.__version__}")
    print(f"Installed backends: {', '.join(available_backends())}")
    frame = cv2.resize(cv2.GaussianBlur(np.random.default_rng(1).integers(0, 255, (480, 640, 3), np.uint8), (7, 7), 0), (640, 480))

    for b in available_backends():
        try:
            det = YoloDetector({**cfg["detector"], "backend": b})
        except Exception as e:
            print(f"  {b:<12} unavailable: {e}")
            continue
        det.detect(frame)
        t = time.perf_counter()
        for _ in range(args.runs):
            det.detect(frame)
        ms = (time.perf_counter() - t) * 1000 / args.runs
        print(f"  detector {b:<12} {ms:7.1f} ms  ->  ~{1000 / ms:4.1f} detections/s  ({cfg['detector']['threads']} threads)")

    lanes = LaneDetector(cfg["lanes"])
    road = synthetic_road(640, 480, 0)
    lanes.process(road)
    t = time.perf_counter()
    for k in range(100):
        lanes.process(road)
    print(f"  lanes                 {(time.perf_counter() - t) * 10:7.1f} ms per frame")


if __name__ == "__main__":
    main()
