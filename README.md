# ODIN — Optical Dual-Spectrum Intelligence Node

ODIN is a TDTH 2026 Hackathon prototype for comparing visible-red and near-infrared-sensitive camera images. It uses OpenCV, NumPy and Flask to display an **experimental vegetation contrast / NDVI estimate** in a browser.

The software can run entirely on a laptop using explicitly labeled synthetic inputs. Physical cameras, lighting, exposure controls and material discrimination still require validation. **Simulation demonstrates the processing pipeline; it is not evidence that the hardware detects camouflage or measures plant health.**

## Start now: no hardware required

Use Python 3.10 or newer (development checks use Python 3.12 with the pinned versions in requirements.txt).

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Then:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -v
python app.py --demo
```

Open **http://127.0.0.1:8080**. Three synthetic regions exercise high, neutral and low estimated NIR contrast. At `k=1`, their unannotated pixels have indices `0.75`, `0.0` and `-0.5`. Text overlays alter some input pixels. All simulated streams carry a small Demo label; the API reports `simulation: true` and `ndvi_online: false`.

The default server binds to the local machine. For a trusted local network, use `--host 0.0.0.0` and open the laptop/Pi's LAN address. This development dashboard has no authentication; it is not a public deployment.

## Camera modes

```bash
# One laptop webcam: RGB preview only, spectral output disabled
python app.py --rgb 0 --noir 0

# Two OpenCV-compatible cameras: preview until calibration exists
python app.py --rgb 0 --noir 1

# Calibrate NoIR -> RGB, then restart the dashboard
python calibrate.py --rgb 0 --noir 1
python app.py --rgb 0 --noir 1 --gain 1.0

# Raspberry Pi CSI camera through optional Picamera2, plus USB RGB webcam
python calibrate.py --rgb 0 --noir picamera2:0
python app.py --rgb 0 --noir picamera2:0
```

**Indices are examples, not known device assignments.** Confirm the actual camera models, IR-cut characteristics, OS and available controls before assigning RGB/NoIR roles. Two ordinary RGB webcams cannot provide a physical NIR measurement. OpenCV sources may also be file paths or stream URLs; prerecorded pairs are not automatically synchronized or looped.

Picamera2 is imported only when a `picamera2:N` source is requested. On Raspberry Pi OS, install the OS-supported packages, typically `sudo apt install python3-picamera2 python3-opencv python3-numpy python3-flask`. If using a virtual environment there, create it with `--system-site-packages`. Verify camera detection with `rpicam-hello --list-cameras`. The adapter is implemented but needs testing on the actual Pi/camera.

### Dashboard states

| State | Behavior |
|---|---|
| `SIMULATION` | Labeled synthetic previews and heatmap; no physical reading |
| `NO SENSORS` | Dashboard remains usable with offline image plates |
| `SINGLE SENSOR` | Available preview shown; heatmap disabled |
| `NOT CALIBRATED` | Both raw previews shown; heatmap disabled |
| `NDVI ONLINE` | Both feeds returned frames and a valid homography is loaded; experimental heatmap enabled |

`NDVI ONLINE` means the software prerequisites are met, **not** that radiometric accuracy or target classification is established. A read failure downgrades the state on the next producer batch. Batches older than two seconds are marked stale. Failed device opens are not automatically retried; resolve the device issue and restart.

## How the estimate works

1. Warp the NoIR image into the RGB image coordinate system using `H`.
2. Read the BGR red channels as floating-point arrays.
3. Estimate `NIR = max(NoIR_red - k * RGB_red, 0)`.
4. Compute `index = (NIR - RGB_red) / (NIR + RGB_red + 1e-7)`.
5. Map the index through the `[-0.2, 1.0]` window using a muted sequential palette.

The display represents lower values with dark charcoal and higher values with warm off-white. The legend samples the same renderer. These colors are index ranges, **not verified material labels**.

Warp borders, near-black combined signals and saturated red channels are excluded from the displayed mean and painted dark gray. The API reports `valid_fraction` and `nir_positive_fraction`; the latter is a diagnostic, not a confidence score. A clipped subtraction is retained in the index and can represent poor gain/lighting as well as low estimated NIR.

Standard NDVI uses calibrated red and NIR reflectance. Consumer-camera output contains sensor-response differences, gamma, exposure and image processing. Subtracting those outputs with one scalar gain does not isolate a guaranteed pure NIR band. Treat this prototype as relative contrast under controlled conditions until measured against reference targets.

## Capture architecture and API

A single producer thread owns both captures, processes one pair and encodes one JPEG for each view. All browser clients consume the same cached batch; opening another panel/client does not add camera reads. Acquisition is sequential and has no hardware synchronization. A blocking camera driver can delay both feeds; stale streams are labeled, but driver recovery may require restart. The NoIR panel remains raw; only the processing path is warped.

| Endpoint | Result |
|---|---|
| `/` | Dashboard, Traditional Chinese / English switch |
| `/api/state` | Status, simulation flag, calibration, gain, window, processed-batch FPS, mean, valid area and errors |
| `/video/rgb` | RGB MJPEG |
| `/video/noir` | NoIR MJPEG |
| `/video/ndvi` | Experimental heatmap or explicit offline plate |

`--fps` limits producer rate; it does not guarantee sensor or processing speed. **30 FPS and <150 MB are design targets, not measured achievements.** Multiple concurrent clients and Pi hardware require performance testing.

### Useful options

```bash
python app.py --demo --width 640 --height 480 --fps 15 --port 8080
python app.py --rgb 0 --noir 1 --gain 1.25 --window=-0.2,1.0
python app.py --homography /path/to/matrix_h.npy
```

`--k` is an alias for `--gain`. `ODIN_K` supplies the default gain. Use the equals form for a negative `--window` argument. Invalid gain/window/matrices are rejected or calibration is kept offline. Calibration is loaded at startup; restart after generating it.

## Team next steps

Follow the [Pi setup, camera bring-up and calibration runbook](docs/HARDWARE_RUNBOOK.md).
The Pi can run the simulation before cameras arrive. For the CAD lead, see the
[mounting checklist and editable fixture base](cad/README.md); final camera
carriers depend on measured hardware dimensions. A [printable textured target](docs/calibration_target.svg)
is included for geometric registration, not radiometric calibration.

## Calibration and hardware bring-up

1. Verify each sensor independently and identify its spectrum/filter configuration.
2. Use stable daylight or controlled NIR illumination. Ordinary indoor LED lighting may provide insufficient NIR.
3. Fix mounts, focus, exposure, white balance and gain. **The current adapter does not automatically lock camera controls.** Configure them using device-supported controls before trusting comparisons.
4. Place a textured planar target at the intended subject distance. Keep both cameras and target still.
5. Run `calibrate.py` with the same sources/resolutions used by the app. It fits **NoIR -> RGB**, requires enough RANSAC inliers, and checks mean reprojection error before saving.
6. Inspect alignment on actual targets. A homography cannot remove depth-dependent parallax; invalid border masking cannot remove internal alignment errors.
7. Tune gain using repeatable reference targets and illumination; compare live foliage and a visually similar artificial target. Do not assume fixed classification thresholds transfer across cameras or scenes.
8. Record the setup, gain, lighting and results. Recalibrate if mounting/focus changes.

`matrix_h.npy` is per setup, gitignored, and defaults to the repository directory. Use `--out` during calibration and `--homography` in the app for another location. See [lighting and measurement notes](docs/LIGHTING.md).

## Repository

| File | Responsibility |
|---|---|
| `engine.py` | Pure array math, warping, rendering and legend |
| `sensors.py` | OpenCV capture and optional Picamera2 adapter |
| `simulation.py` | Deterministic synthetic frame pairs |
| `app.py` | Shared producer, readiness, cached streams and Flask API |
| `calibrate.py` | ORB matching, RANSAC and reprojection diagnostics |
| `test_engine.py`, `test_app.py` | Camera-free numeric, state, stream and calibration regression tests |
| `templates/index.html`, `static/style.css` | Compact desktop dashboard; stacked mobile layout |
| `docs/HARDWARE_RUNBOOK.md`, `docs/calibration_target.svg` | Pi bring-up and calibration procedure / printable texture |
| `cad/` | Provisional adjustable base and measurement checklist |
| `.github/workflows/tests.yml` | Camera-free software checks on pushes and PRs |

## Before submission

- Run the test suite and rehearse the synthetic mode on the presentation laptop.
- If hardware arrives, prove capture and stable target contrast before making detection claims.
- Prepare a short recording of any successful physical demo as a fallback.
- Clearly distinguish software simulation, physical observations and future performance goals in the pitch.

## References

- [USGS: NDVI and red/NIR reflectance](https://www.usgs.gov/landsat-missions/landsat-normalized-difference-vegetation-index)
- [Raspberry Pi camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)

The Inter font is hosted locally in `static/fonts/` under the included SIL Open Font License.
