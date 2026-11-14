# KARP Troubleshooting & Diagnostics Guide

This document assists developers and field operators in troubleshooting network connectivity, video streaming latency, GPU initialization, serial errors, and GPS fix issues.

---

## 1. Network & Streaming Issues

### Symptom: Raspberry Pi shows "AI Disconnected" banner
1. **Verify Laptop IP**: Open Tab 7 (Settings) on the Raspberry Pi GUI and confirm the Laptop IP address matches the current IP reported by `ipconfig` (Windows) or `ip addr` (Linux) on the laptop.
2. **Ping Test**:
   ```bash
   ping <laptop_ip>
   ```
3. **Check Firewall**: Ensure Windows Defender Firewall or `ufw` on Linux is not blocking port `5000`, `5001`, or `8765`.
   - Windows quick rule: Run PowerShell as Admin:
     ```powershell
     New-NetFirewallRule -DisplayName "KARP ADAS" -Direction Inbound -Protocol TCP -LocalPort 5000,5001,8765 -Action Allow
     New-NetFirewallRule -DisplayName "KARP ADAS UDP" -Direction Inbound -Protocol UDP -LocalPort 5000,5001 -Action Allow
     ```

### Symptom: High Video Latency (>150ms) or Video Freezes
- Ensure both devices are connected to **5 GHz Wi-Fi** or direct Gigabit Ethernet. 2.4 GHz Wi-Fi suffers heavy packet collisions.
- Lower resolution to `640x360` or `1280x720` in `shared/config/default_config.json`.
- The system automatically drops stale frames if the frame queue exceeds 2 frames. Look at the reception FPS vs pipeline latency metrics on Tab 2 (Live Vision).

---

## 2. Computer Vision & GPU Issues

### Symptom: Laptop falls back to CPU instead of NVIDIA RTX 4050
- Run `nvidia-smi` to verify driver state.
- Test CUDA from Python:
  ```python
  import torch
  print(torch.cuda.is_available())
  ```
- If torch CUDA is false, reinstall torch with the official CUDA index:
  `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`
- KARP provides automatic CPU fallback with ONNX Runtime and OpenCV DNN to guarantee non-stop execution.

---

## 3. Serial & ESP32 Issues

### Symptom: "ESP32 Disconnected" warning on HMI
1. Check if the ESP32 USB cable is a data-capable cable (many micro-USB cables are charge-only).
2. Check serial port name:
   - On Linux (Pi): Run `ls /dev/ttyUSB* /dev/ttyACM*`. If permission denied, ensure user is in `dialout` group (`sudo usermod -a -G dialout $USER` followed by re-login).
   - On Windows: Check Device Manager under "Ports (COM & LPT)".
3. If no physical hardware is plugged in, enable **Simulation Mode** in Tab 7 or start with `--simulation`.

### Symptom: GPS Fix Quality stays at 0 / Invalid
- GPS antennas require line-of-sight to the open sky. Indoor testing will report `fix_quality: 0`.
- Use the built-in GPS simulator for indoor demonstration: the GUI provides clear indicators distinguishing between live satellite fixes and simulated GPS trajectories.
