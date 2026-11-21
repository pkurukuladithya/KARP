# KARP Pi Brain: standalone ADAS on a Raspberry Pi 4B

This runs lane detection, object detection and collision warnings on a Raspberry Pi 4B with one camera. It needs no laptop, GPU or network.

## Is a Pi 4B fast enough?

Yes, if the work is split so that slow parts never stall the screen.

| Part | How it runs | Expected on a Pi 4B |
|---|---|---|
| Camera + display | Own threads, always the newest frame | 25–30 fps |
| Lane detection | Classical vision (no neural net), at 320 px width | 3–10 ms/frame, every frame |
| Object detection | YOLO11n at 320×320 on CPU (NCNN or ONNX Runtime, 3 cores) | about 6–12 detections/s |
| Boxes between detections | Tracker predicts each box's motion | Boxes move smoothly at display rate |

These Pi figures are **estimates** until you run `tools/benchmark.py` on your Pi, which prints real numbers.

What you trade compared with the RTX 4050 version:
- A smaller model (YOLO11n instead of YOLO11s).
- Shorter detection range: small, far objects (beyond about 40–50 m) get missed at 320 px.
- Detections update about 8 times a second instead of 25.

That is still usable for a demo or prototype ADAS. **It is not a certified safety system.**

## Architecture

```
 Camera thread ──► newest frame ──┬──► Display loop (camera fps)
 (USB/CSI, MJPG)                  │      lanes (every frame) + HUD + alerts
                                  │      draws the latest tracks, motion-predicted
                                  └──► Detector thread (as fast as the CPU allows)
                                         YOLO11n → tracker → distance → TTC
```

No queues anywhere: a slow consumer skips frames instead of building up lag.

## Hardware notes

- **64-bit Raspberry Pi OS (Bookworm)**. Check with `uname -m`, which must say `aarch64`. The fast backends (NCNN, ONNX Runtime) need a 64-bit OS.
- **3.5" RPi LCD (480x320) or HDMI Display**: Native output is tailored to 480x320 resolution with single-tap view switching.
- **Heatsink + fan**. The detector keeps 3 cores busy, and without cooling the Pi throttles at 80 °C and slows down. The HUD shows the CPU temperature.
- **Camera:** a USB webcam (MJPG capable) or the Pi Camera Module (`--source picam`).
- **Power:** an official 5 V 3 A supply.

## Install on the Pi (one time)

```bash
cd ~/KARP && git pull
cd pi_brain
bash setup_pi.sh
```

This creates `.venv`, installs numpy, OpenCV, ONNX Runtime and NCNN, and finishes by running a benchmark of your Pi. The model files are already in `pi_brain/models`, so no download is needed.

## Run

On the Pi's desktop (3.5" LCD or car display):
```bash
cd ~/KARP/pi_brain
bash run.sh                      # window (fitted to 480x320 display)
bash run.sh --fullscreen         # kiosk mode (fills 3.5" LCD completely)
bash run.sh --view map           # start directly in Navigation Map mode
bash run.sh --view split         # start in Split mode (Vision + Map)
bash run.sh --web 8080           # plus a live view at http://<pi-ip>:8080 on a phone
bash run.sh --headless --web 8080   # no monitor attached
bash run.sh --source picam       # Pi Camera Module instead of USB
bash run.sh --source drive.mp4   # test with a dash-cam video
bash run.sh --source synthetic   # no camera at all
```

Window keys & Controls:

| Control | Action |
|---|---|
| **Mouse Click / Tap** | **Cycle views: VISION -> MAP -> SPLIT** |
| `m` | **Cycle views: VISION -> MAP -> SPLIT** |
| `q` / `Esc` | Quit |
| `f` | Fullscreen toggle |
| `d` | Detection on/off |
| `l` | Lanes on/off |
| `s` | Snapshot |

Every 5 s the terminal prints a line like this:
```
STATUS | mode VISION | camera 30.0 fps | display 29.8 fps | AI 8.4 fps, 105 ms [ncnn] | lanes 6.1 ms | CPU 62C
```

## ESP32 sensor hub (USB serial)

The ESP32-S3 firmware in `esp32_firmware/` adds GPS (NEO-6M), road vibration (MPU6050), status LEDs and a buzzer. It is optional, and pi_brain never invents sensor values:

| Situation | Speed | Map / GPS | Road |
|---|---|---|---|
| ESP32 not connected | `--` NO ESP32 | "ESP32 NOT CONNECTED", home area, no vehicle marker | ESP32 OFF |
| ESP32 online, GPS module sends nothing | `--` NO GPS DATA | "GPS NO DATA" | from MPU |
| GPS searching for satellites | `--` GPS CONNECTING | "GPS CONNECTING..." (last real fix in grey, if any) | from MPU |
| GPS fix, car standing still | `0` STATIONARY | live position | from MPU |
| GPS fix, car moving | real GPS speed | live position, heading, trail | from MPU |

**Standing still** is confirmed with the MPU6050. If the MPU feels almost no vibration (< 0.03 g) and GPS reports under 8 km/h, the speed shows 0. This hides the GPS drift a parked car shows. The firmware's own moving/stationary decision (GPS speed plus vibration) is also respected.

**Connect:** plug the ESP32-S3's USB port into the Pi. It appears as `/dev/ttyACM0` (native USB) or `/dev/ttyUSB0` (CP210x/CH340 boards). With `"esp32_port": "auto"` in `config.json`, pi_brain finds it by its USB ID. It reconnects by itself if the cable is unplugged or the ESP32 resets.

**Check the link on its own** (no camera or AI needed):
```bash
python tools/esp32_monitor.py --list              # the ESP32 should be marked "<- Espressif ..."
python tools/esp32_monitor.py                     # decoded GPS / MPU / road data every second
python tools/esp32_monitor.py --test-actuators    # yellow LED + beep, then red blink + beeps
```

**Data flow:**

| Direction | What |
|---|---|
| ESP32 → Pi, 5 Hz | `{"type":"sensor_telemetry", ...}`: GPS fix, speed, satellites, acceleration, vibration, road class, pothole event |
| ESP32 → Pi, at boot | `boot`, `status` (MPU calibration) and `error` messages, logged in the terminal |
| Pi → ESP32 | `{"cmd":"actuate","level":"CRITICAL"/"WARNING","buzzer_ms":N}`: red LED blinks + beeps for CRITICAL, steady yellow LED + one beep for a new WARNING. Sent at most every 0.4 s. |

The ESP32 counts as online only while telemetry keeps arriving. After 1.5 s without data it is shown offline, and after 5 s the port is reopened. Every 5 s the terminal prints an `ESP32 |` status line.

| Problem | Fix |
|---|---|
| `No permission for /dev/ttyACM0` | `sudo usermod -aG dialout $USER`, then reboot (`setup_pi.sh` does this) |
| `... is in use by another program` | Close `pio device monitor`, Arduino serial monitor, or `raspberry_pi/main.py` |
| `GPS module not sending` | Check GPS TX → GPIO18 and the GPS module's power |
| `GPS searching` for a long time | Needs open sky; a cold start takes 1–5 minutes |
| `MPU ERROR` | Check SDA → GPIO8, SCL → GPIO9 and 3.3 V; then press the ESP32 reset button |
| No ESP32 hardware but want to test | `python tools/esp32_emulator.py`, then `bash run.sh --esp-port socket://127.0.0.1:7000` |

## Calibrate for your car (`config.json`)

| Setting | What to set |
|---|---|
| `display.mode` | Initial view: `vision`, `map`, or `split`. |
| `display.width` / `height` | Target display output (default: 480x320 for 3.5" LCD). |
| `telemetry.latitude/longitude` | Map area shown before the first GPS fix (no vehicle marker is drawn there). |
| `geometry.camera_height_m` | Lens height above the road. Distance accuracy depends on it. |
| `geometry.pitch_deg` | Downward tilt of the camera (0 = level). |
| `geometry.hfov_deg` | Your camera's horizontal field of view (most webcams are 60–78°). |
| `lanes.roi_top` | Fraction of image height where the road search starts (just below the horizon). |
| `lanes.departure_ratio` | Lower = earlier lane-departure warning. |
| `alerts.*` | TTC and distance thresholds for the warnings. |
| `detector.threads` | 3 on a Pi 4B (leaves one core for camera + display). |
| `detector.backend` | `auto` times all installed backends at startup and keeps the fastest. |

## Warnings produced

- **BRAKE! / COLLISION RISK**: a vehicle in your lane with time-to-collision below 1.6 s / 2.8 s.
- **TOO CLOSE**: a vehicle in your lane closer than 6 m.
- **PEDESTRIAN AHEAD**: a person in your path within 15 m (critical under 7.5 m).
- **LANE DEPARTURE LEFT/RIGHT**: both lane lines must have been tracked stably first.
- **RED LIGHT AHEAD**, **STOP SIGN**.

## Tests

```bash
python -m pytest pi_brain/tests -q
```
