# KARP Deep Learning Model Specifications & Artifacts

This directory documents the neural network architectures, pretrained models, datasets, licenses, and installation instructions for KARP.

---

## 1. Supported Model Backends & Pipelines

### A. Object Detection & Tracking
- **Default / Recommended**: YOLOv8n / YOLOv11n exported to ONNX format (`yolov8n.onnx` or `yolov11n.onnx`).
- **Dataset**: MS COCO (80 classes) filtered to automotive classes (car, truck, bus, motorcycle, bicycle, pedestrian, traffic sign, traffic light).
- **Inference Runtime**:
  - NVIDIA RTX 4050 Laptop GPU: ONNX Runtime with `CUDAExecutionProvider` / TensorRT or PyTorch with CUDA 12.1.
  - Fallback: CPU with OpenVINO / `CPUExecutionProvider`.
- **License**: AGPL-3.0 / Enterprise Commercial (Ultralytics).
- **Download Instructions**:
  ```bash
  pip install ultralytics
  yolo export model=yolov8n.pt format=onnx imgsz=640
  cp yolov8n.onnx laptop_vision/models/
  ```

### B. Lane Detection
- **Primary Algorithm**: 2nd-Degree Polynomial Sliding Window with Inverse Perspective Mapping (IPM) in `laptop_vision/lane_detection/polynomial_lane_detector.py`. Real-time (~200 FPS on RTX 4050), robust on standard highway curves.
- **Deep Learning Alternative**: Ultra-Fast-Lane-Detection-v2 (CULane / TuSimple benchmark).
- **License**: Apache 2.0 / BSD 3-Clause.

### C. Traffic Sign Classification
- **Dataset**: German Traffic Sign Recognition Benchmark (GTSRB) / LISA Traffic Sign Dataset.
- **Classes**: Speed limits (30, 50, 60, 80), Stop signs, Yield, Pedestrian crossings.
- **Approach**: Multi-stage (spatial color/contour isolation + shape classification).

### D. Traffic Light Classification
- **Approach**: Vertical spatial-slot colorimetric energy classifier (isolates illuminated lamp position and color saturation: Red top, Yellow middle, Green bottom).
- **Safety Rule**: If confidence is ambiguous or lighting is uncertain, state is classified as `UNKNOWN` rather than guessing a false positive green/red signal.

---

## 2. Expected Real-World Limitations

1. **Weather & Lighting Degradation**: Heavy rain, unlit country roads at night, or blinding direct sun glare can obscure camera lane markings. The system will report `confidence < 0.40` and transition to search mode.
2. **Monocular Distance Approximation**: Distance is estimated using calibrated road-plane geometry ($h_{cam} = 1.25m$, $\theta_{pitch} = 2.0^\circ$). Severe road inclines (steep hills or speed humps) cause transient distance estimation shifts. All distances are explicitly marked as approximate on the HMI.
3. **Hardware Acceleration**: The system auto-detects CUDA on startup. If running without NVIDIA drivers or on a non-GPU host, the pipeline automatically falls back to CPU execution without throwing runtime exceptions.
