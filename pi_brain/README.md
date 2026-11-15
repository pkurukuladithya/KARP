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

On the Pi's desktop (monitor or car display):
```bash
cd ~/KARP/pi_brain
bash run.sh                      # window
bash run.sh --fullscreen         # kiosk
bash run.sh --web 8080           # plus a live view at http://<pi-ip>:8080 on a phone
bash run.sh --headless --web 8080   # no monitor attached
bash run.sh --source picam       # Pi Camera Module instead of USB
bash run.sh --source drive.mp4   # test with a dash-cam video
bash run.sh --source synthetic   # no camera at all
```

Window keys:

| Key | Action |
|---|---|
| `q` / `Esc` | Quit |
| `f` | Fullscreen |
| `d` | Detection on/off |
| `l` | Lanes on/off |
| `s` | Snapshot |

Every 5 s the terminal prints a line like this:
```
STATUS | camera 30.0 fps | display 29.8 fps | AI 8.4 fps, 105 ms/inference, result age 140 ms [ncnn] | lanes 6.1 ms | CPU 62C
```

Judge smoothness on the Pi's own screen or in the `--web` view, **not over VNC**. VNC competes with the ADAS for CPU.

## Calibrate for your car (`config.json`)

| Setting | What to set |
|---|---|
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

## Other model sizes (optional, on the laptop)

```bash
python pi_brain/tools/export_model.py --imgsz 256              # faster, shorter range
python pi_brain/tools/export_model.py --imgsz 416              # slower, longer range
```

Then update `input_size` and the model paths in `config.json`, and `git pull` on the Pi.

## Tests

```bash
python -m pytest pi_brain/tests -q
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot open a window` | Run from the Pi desktop, or `bash run.sh --headless --web 8080`. Check that `opencv-python-headless` is not installed. |
| `camera '0' not available` | Run `v4l2-ctl --list-devices` and use `--source /dev/videoN`. |
| AI below 5 fps | Run `tools/benchmark.py`, check the CPU temperature (cooling), close VNC and the browser. |
| Lanes never "OK" | Lower `lanes.roi_top`, and check that the camera sees the road (not the bonnet). |
| Distances wrong | Set `camera_height_m`, `pitch_deg` and `hfov_deg`. |
