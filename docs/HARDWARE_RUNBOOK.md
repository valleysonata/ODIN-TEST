# Hardware bring-up and demo runbook

Current inventory: Raspberry Pi has arrived; camera models, USB webcam specifications and final mounting geometry are not confirmed. Complete stages in order. Software simulation is available throughout.

## 1. Prepare the Pi now (no cameras)

Record the board model and OS:

```bash
cat /proc/device-tree/model
cat /etc/os-release
python3 --version
hostname -I
```

If boot media is blank, use Raspberry Pi Imager, choose the correct board and recommended Raspberry Pi OS, and configure username, Wi-Fi and SSH. Do not re-image a working card just to run ODIN. Boot with a suitable supply and a nonconductive support/case.

On Raspberry Pi OS:

```bash
sudo apt update
sudo apt install git python3-picamera2 python3-opencv python3-numpy python3-flask v4l-utils
```

Use the OS packages for the camera stack; do not install the laptop's pinned pip environment over the system environment. Picamera2/libcamera bindings come from the Pi OS installation. If using a virtual environment, create it with `python3 -m venv --system-site-packages .venv` (install `python3-venv` if needed).

After these changes have been pushed:

```bash
git clone https://github.com/valleysonata/ODIN-TEST.git
cd ODIN-TEST
python3 -m unittest discover -v
python3 app.py --demo --host 0.0.0.0
```

For an existing checkout, inspect `git status`, preserve any local work, then use `git pull --ff-only`. If the push is still pending, transfer the provided source ZIP instead: the original repository has no `--demo` flag.

Open `http://<PI-IP>:8080` on a laptop on the same network. Check all three watermarked streams, the language switch, state polling and SIMULATION badge. Campus Wi-Fi may isolate devices; use Ethernet or a shared hotspot if the devices cannot reach one another. Keep a laptop demo fallback.

Acceptance: tests pass on the Pi, all three browser streams load, status says SIMULATION, and mean/FPS update. This proves the software deployment, not spectral sensing.

## 2. Identify cameras when they arrive

Before connecting a CSI ribbon, shut down and unplug the Pi. Check the actual model: Pi 4 and earlier flagship boards use a 15-pin camera connector; Pi 5 and Zero boards use a 22-pin mini connector and need an appropriate cable to the camera. Follow the official installation guide for orientation.

Record:

| Item | Fill in before mounting |
|---|---|
| Pi model / OS | |
| NoIR model and variant / confirmed absence of IR-cut | |
| USB webcam model / confirmed visible-only role | |
| Lens field of view and focus behavior | |
| Actual frame sizes | |
| Exposure / gain / white-balance controls | |
| PCB dimensions / hole centers / screw clearance | |
| Webcam housing envelope / lens center / mounting feature | |
| Ribbon type / USB cable routing / power supply | |

Detection commands:

```bash
rpicam-hello --list-cameras
lsusb
v4l2-ctl --list-devices
```

`/dev/video0` is only an example. CSI-related video nodes can also exist; identify the webcam from `v4l2-ctl --list-devices`, not the lowest index. Use a stable `/dev/v4l/by-id/...` path if available.

For a headless CSI smoke test:

```bash
rpicam-still --nopreview --timeout 2000 --output /tmp/odin-noir.jpg
```

Check the saved image. Camera discovery does not by itself prove a usable capture stream.

Run the dashboard with the actual sources. Example only:

```bash
python3 app.py --rgb /dev/video0 --noir picamera2:0 --host 0.0.0.0
```

Before calibration, expect NOT CALIBRATED and an offline heatmap. Verify both raw views individually. If one source cannot open, fix acquisition before attempting calibration. Restart after resolving failed opens; reconnect is not automatic.

## 3. Finalize the mount

Use [the CAD checklist](../cad/README.md). Start with a rigid provisional fixture, then measure the actual hardware before fitting/printing camera carriers. Keep lenses parallel, at similar height and as close as housings allow; the project target is <25 mm lens-center spacing, not PCB-edge spacing. Document the actual spacing if that target is infeasible.

Strain-relieve cables independently, allow airflow, and support the NoIR PCB on insulated standoffs without loading the sensor or ribbon connector. Leave adjustment for alignment, then lock the fixture. Calibration happens after final mounting, focus and capture settings are fixed.

## 4. Geometric calibration

Use stable light, stationary cameras and a textured planar target at the planned demo distance. [The provided target](calibration_target.svg) is a printable starting point; a homography does not require known square dimensions. Verify texture is visible in both raw feeds. Some inks/materials lose contrast under NIR.

Stop the dashboard with Ctrl+C first so calibration has exclusive camera access.

```bash
python3 calibrate.py --rgb /dev/video0 --noir picamera2:0 --width 640 --height 480
```

The script fits NoIR -> RGB, reports RANSAC inliers and mean reprojection error, and writes `matrix_h.npy` only after its checks pass. Repeated frame matches are correlated; the inlier count is not an independent accuracy estimate. A successful fit still needs visual inspection over the scene and repeatability testing.

If calibration fails: improve distinctive texture, focus and common field of view; hold everything still; match target distance; verify source roles. Do not lower thresholds merely to force a pass.

Restart with the same resolution:

```bash
python3 app.py --rgb /dev/video0 --noir picamera2:0 --width 640 --height 480 --host 0.0.0.0
```

The homography loads only at startup. Calibration is specific to the source pair, resolution, focus, mounting geometry and depth. Recalibrate when those change. The app requests a resolution but drivers may choose another; inspect actual capture sizes before assuming a saved calibration is compatible.

## 5. Radiometric checks (separate from geometric calibration)

Use daylight or characterized visible + NIR lighting. Inspect camera controls, then freeze exposure, gain and white balance using device-supported settings. The capture adapter does not currently apply those settings automatically. For a USB example:

```bash
v4l2-ctl -d /dev/video0 --list-ctrls
```

Do not copy control values from another webcam: names, units and supported ranges vary. For a CSI camera, use supported Picamera2 controls and make sure calibration and runtime use the same focus/crop. Module 3 autofocus can change the geometry; it needs device-specific handling once identified.

Compare independent reference targets under unchanged settings. Change `--gain` only using a recorded calibration procedure; restart after gain changes. Check `valid_fraction`, `nir_positive_fraction`, repeatability and spatial artifacts. A positive subtraction alone does not prove NIR; a high index alone does not prove healthy foliage. See [measurement notes](LIGHTING.md).

## 6. Rehearse and submit

Use a static scene with real foliage, a visually similar artificial target, and a reference background. Report what you actually observe. Make a 30–60 second recording if physical contrast is repeatable. Keep the labeled simulation available if acquisition or lighting fails.

Before submission: run tests, verify the dashboard from the presentation laptop, record software commit/settings/lighting, rehearse the pitch and check required submission fields. Reserve the final hour before October 4, 2026 at 11:30 Asia/Taipei for submission rather than new features.

Suggested pitch: "ODIN demonstrates a lightweight dual-camera spectral processing pipeline. We estimate relative vegetation contrast using a NoIR/RGB pair; calibrated accuracy and general material detection are future validation work."

## Official references

- [Raspberry Pi getting started](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Camera hardware and ribbon installation](https://www.raspberrypi.com/documentation/accessories/camera.html)
- [Camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
