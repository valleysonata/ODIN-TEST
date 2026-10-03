# Lighting, gain and calibration

Read this before the demo. Four things break NDVI in the field, and none of
them are visible in the code.

---

## 1. The light source is the single biggest failure mode

NDVI here is `NIR = Red_NoIR − k·Red_USB`. That term only exists if the scene
is actually illuminated with near-infrared.

| Source | NIR above 750 nm |
|---|---|
| Sunlight | strong |
| Incandescent / tungsten | strong |
| 850 nm IR illuminator | strong (by design) |
| White LED | **essentially none** |
| Fluorescent | **essentially none** |
| Phone flash / screen | none |

Under a white LED, `Red_NoIR ≈ Red_USB`, so `NIR ≈ 0`, so

```
NDVI = (0 − Red) / (0 + Red) = −1
```

Every pixel saturates to dark blue — **including a healthy live plant**. This
is not a calibration problem and no value of `k` fixes it.

### First test when hardware arrives

Point the NoIR camera at a green leaf. Compare the red channel under a desk
lamp versus in daylight. If the red channel does not rise substantially in
daylight, stop and investigate the light source before touching anything else.

### Options for an indoor demo

- Position the setup next to a window in direct daylight.
- Take the demo outside.
- Add an 850 nm IR illuminator (~$5). Note it lights a *small* area — bring
  the subject close.

**Check the NIR is non-zero:** `engine.nir_valid_mask()` returns the pixels
where the subtraction did not clip. If it is almost empty, there is no NIR in
the scene.

---

## 2. Tuning the radiometric gain `k`

`k` balances two different sensors. Tune it once per illuminant.

1. Point both cameras at a **spectrally neutral** target filling the frame:
   a grey card, white paper, or dry bare dirt. Not grass, not a green leaf.
2. Lock **both** cameras: manual exposure, manual white balance, fixed gain.
   If either auto-adjusts, `k` is wrong on the very next frame.
3. Run with a candidate `k` and read `mean_ndvi` on `/api/state`.
4. Adjust `--gain` until the neutral target reports **≈ 0.0**.
5. Sanity-check: a live green leaf should then read **> 0.5**.

```bash
python app.py --gain 1.25
```

Persist it:

```bash
export ODIN_K=1.25      # read by app.py as the default
```

### Why one scalar is only an approximation

The mismatch between the sensors is *spectrally shaped*: different quantum
efficiency curves, different Bayer dye transmissions, different lens coatings.
A single `k` cancels the offset for the spectrum you tuned on and drifts for
everything else. Vegetation (very high NIR) and soil (low NIR) will each be
off, in opposite directions.

If accuracy matters, match the per-channel transfer curves instead — collect a
grey ramp (or a series of grey patches) and apply histogram/CDF matching per
channel before the subtraction. That costs an afternoon and removes most of
the residual bias.

---

## 3. White balance and exposure must actually be frozen

`awb_auto_is_greyworld=1` does **not** lock white balance. The name means
*"auto-AWB should assume the scene average is grey"* — AWB still runs and
still adapts frame to frame. With a drifting gain, a single `k` cannot hold.

On Raspberry Pi OS Bookworm (libcamera stack), freeze controls explicitly:

```python
from picamera2 import Picamera2
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
picam2.start()
picam2.set_controls({
    "AwbEnable": False,
    "AwbGains": (1.5, 1.3),       # tune for your scene
    "AeEnable": False,
    "ExposureTime": 10000,        # µs
    "AnalogueGain": 1.0,
})
```

For the USB webcam, use `v4l2-ctl` — but control names are driver-specific and
cheap webcams often do not expose them:

```bash
v4l2-ctl -d /dev/video0 --list-ctrls              # see what actually exists
v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=1
v4l2-ctl -d /dev/video0 --set-ctrl=white_balance_automatic=0
```

If a control is missing, that camera cannot be locked — pick another one.

---

## 4. Calibration is depth-dependent

`calibrate.py` fits a **homography**: a transform that maps a single plane
exactly. The two lenses are ~2.5 cm apart, so they see the scene from
different positions. That offset — parallax — grows as the subject gets
closer, and no single 3×3 matrix can correct it.

Practical consequences:

- **Calibrate on a textured, roughly planar target at the distance you will
  actually shoot at.** Not a blank sheet of paper: ORB needs texture, and
  RANSAC needs ≥ 4 non-collinear inliers. Use a checkerboard or ChArUco board.
- **Expect error to grow** for subjects much nearer or farther than the
  calibration distance. Edge fringing in the NDVI is usually registration
  error, not real signal.
- **Recalibrate** whenever the bracket, lens focus or camera positions move —
  including after transport.

The script refuses to save when inliers are too few or reprojection error is
too high, and prints why. Do not lower the thresholds to make it pass; fix the
target.

For better alignment than a homography provides, calibrate intrinsics and
rectify both streams (`cv2.initUndistortRectifyMap` → `cv2.remap`) so the pair
shares an epipolar geometry. Residual offset then becomes a horizontal
disparity rather than an arbitrary warp.
