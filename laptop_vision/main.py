"""
Laptop AI Co-Processor Main Entry Point.
Executes deep neural network perception, lane detection, object tracking, and return video broadcasting.
"""

from __future__ import annotations
import argparse
import logging
import signal
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.config.system_config import get_config
from laptop_vision.pipeline import ADASPipelineOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("KARP.LaptopVision")


def parse_args():
    parser = argparse.ArgumentParser(description="KARP ADAS — Laptop GPU Perception Engine")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind stream receiver")
    parser.add_argument("--port", type=int, default=5000, help="Camera video reception port (Pi -> Laptop)")
    parser.add_argument("--target-ip", type=str, help="Raspberry Pi IP address to stream annotated video back to")
    parser.add_argument("--target-port", type=int, default=5001, help="Return video stream port (Laptop -> Pi)")
    parser.add_argument("--ws-port", type=int, default=8765, help="Telemetry WebSocket port")
    parser.add_argument("--force-cpu", action="store_true", help="Force CPU inference fallback")
    return parser.parse_args()


def main():
    args = parse_args()
    config = get_config()

    target_ip = args.target_ip or config.get("network", "pi_ip", "127.0.0.1")
    use_cuda = not args.force_cpu

    logger.info("==========================================================")
    logger.info("        KARP ADAS — Laptop AI Perception Engine           ")
    logger.info("==========================================================")
    logger.info(f"Video Reception Port : {args.port}")
    logger.info(f"Return Video Target  : {target_ip}:{args.target_port}")
    logger.info(f"WebSocket Port       : {args.ws_port}")
    logger.info(f"Acceleration Mode    : {'CUDA GPU (RTX 4050)' if use_cuda else 'CPU Only'}")

    orchestrator = ADASPipelineOrchestrator(
        rx_host=args.host,
        rx_port=args.port,
        tx_target_ip=target_ip,
        tx_port=args.target_port,
        ws_port=args.ws_port,
        use_cuda=use_cuda,
    )

    def handle_exit(sig, frame):
        logger.info("Shutdown signal received. Stopping perception pipeline...")
        orchestrator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    orchestrator.start()
    logger.info("Perception pipeline running. Waiting for camera stream...")

    try:
        while orchestrator.running:
            orchestrator.step(timeout=0.05)
            # Yield minimal CPU time when queue is idle
            time.sleep(0.002)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt. Cleaning up...")
    finally:
        orchestrator.stop()


if __name__ == "__main__":
    main()
