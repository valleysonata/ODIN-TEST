# Lighting and measurement notes

ODIN estimates a spectral index from two consumer-camera red channels. It is not yet a calibrated reflectance instrument. The current physical camera models and their spectral responses are unknown.

## Illumination

The scene needs both visible red and near-infrared illumination. Sunlight is a practical first test. Many indoor white LEDs supply little useful NIR, so healthy leaves can also produce low or negative estimates. An appropriate NIR illuminator may support indoor testing, but its intensity, geometry and balance with visible light need characterization.

A positive subtraction does not prove the presence of NIR: mismatched exposure or camera processing can also cause it. Conversely, clipping to zero does not identify water or any other material.

## Exposure and gain

Both cameras must use stable exposure, white balance and gain for repeatable comparisons. The software does not automatically freeze these controls: their names and supported ranges vary by device. Determine the actual webcam and Pi camera models first. For Picamera2, inspect supported controls and use `AeEnable`, `AwbEnable`, `ExposureTime`, `AnalogueGain` and `ColourGains` as supported by the installed version. USB controls should be inspected with the device's driver tools.

`--gain` / `--k` adjusts one scalar in `max(NoIR_red - k*RGB_red, 0)`. It cannot correct arbitrary spectral sensitivity differences, nonlinear transfer functions or automatic image processing. Do not tune merely until a plant turns red; that would bake the desired answer into the demonstration. Record fixed settings and compare several independent reference targets under the same light.

Neutral gray/soil targets do not universally have NDVI zero. Do not force a zero reading without a measured reference. Histogram matching also does not establish physical radiometric calibration.

## Spatial registration

Calibration estimates NoIR -> RGB on a textured, static plane. Match the target distance to the demonstration distance; repeated checkerboard patterns can produce ambiguous ORB matches, so prefer distinctive texture and visually inspect the result. The script's inlier count and reprojection error are diagnostics, not proof of accurate alignment over a 3D scene.

The runtime masks warp borders, near-black combined signals and saturated red channels. It does not remove parallax, internal misregistration or all lens distortion. There is no hardware frame synchronization. Keep subjects still, minimize lens baseline, and recalibrate after mount/focus changes.

## What to report

Present this as an experimental vegetation contrast index until validated with known red/NIR reflectance references. Record lighting, sensor/filter models, capture settings, geometry, gain and repeatability. Avoid absolute plant-health scores or guaranteed plastic/camouflage detection. Material reflectance varies, and a low index alone does not identify a material.

References: [USGS NDVI](https://www.usgs.gov/landsat-missions/landsat-normalized-difference-vegetation-index), [Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf).
