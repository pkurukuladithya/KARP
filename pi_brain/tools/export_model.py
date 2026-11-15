"""
Export a YOLO model into Pi-friendly CPU formats (ONNX + NCNN) at a small input size.

Run this on the LAPTOP (it has ultralytics + torch), then commit/copy pi_brain/models
to the Pi. The Pi itself never needs torch or ultralytics.

    python pi_brain/tools/export_model.py                 # yolo11n @ 320 (recommended)
    python pi_brain/tools/export_model.py --imgsz 256     # faster, shorter range
    python pi_brain/tools/export_model.py --model yolo11s.pt --imgsz 320   # slower, more accurate
"""

from __future__ import annotations
import argparse
import shutil
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


def main() -> None:
    ap = argparse.ArgumentParser(description="Export YOLO to ONNX/NCNN for Raspberry Pi CPU inference")
    ap.add_argument("--model", default="yolo11n.pt", help="Ultralytics weights (auto-downloaded if missing)")
    ap.add_argument("--imgsz", type=int, default=320, help="Square input size (multiple of 32)")
    ap.add_argument("--no-ncnn", action="store_true", help="Only export ONNX")
    args = ap.parse_args()

    from ultralytics import YOLO  # laptop-only dependency

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(args.model).stem
    tag = f"{stem}_{args.imgsz}"

    # Work in a temp copy so the exported files land next to the weights, then move them.
    model = YOLO(args.model)

    onnx_path = Path(model.export(format="onnx", imgsz=args.imgsz, opset=12, simplify=True, dynamic=False))
    dst_onnx = MODELS_DIR / f"{tag}.onnx"
    shutil.copy2(onnx_path, dst_onnx)
    print(f"[OK] ONNX  -> {dst_onnx} ({dst_onnx.stat().st_size / 1e6:.1f} MB)")

    if not args.no_ncnn:
        try:
            ncnn_dir = Path(model.export(format="ncnn", imgsz=args.imgsz))
            dst_dir = MODELS_DIR / f"{tag}_ncnn"
            dst_dir.mkdir(exist_ok=True)
            for name in ("model.ncnn.param", "model.ncnn.bin"):
                shutil.copy2(ncnn_dir / name, dst_dir / name)
            print(f"[OK] NCNN  -> {dst_dir}")
        except Exception as e:  # NCNN is optional; ONNX Runtime works everywhere
            print(f"[WARN] NCNN export failed ({e}); the Pi will use ONNX Runtime instead.")


if __name__ == "__main__":
    main()
