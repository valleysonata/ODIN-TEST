"""Pure array operations for ODIN's experimental spectral index.

NoIR red contains visible red and NIR sensitivity; subtracting scaled RGB red
produces an approximation, not calibrated pure NIR reflectance. Consumer camera
processing and different spectral responses can bias the result. See README.
No capture or filesystem I/O is performed here.
"""
from __future__ import annotations

import cv2
import numpy as np

# NDVI -> colour window.
#
# This is deliberately NOT [-1.0, +1.0].  cv2.applyColorMap(COLORMAP_JET)
# puts *green* at the midpoint, so mapping the full theoretical range makes
# bare soil (NDVI ~ 0.0) land on 127 and render green -- which reads as
# "stressed vegetation".  Starting the ramp at -0.2 pushes soil/water down
# into the blue end so the legend matches what the operator actually sees.
DEFAULT_WINDOW: tuple[float, float] = (-0.2, 1.0)

# Guard against 0/0 on pixels where both channels read black.
EPS = 1e-7


def align(frame: np.ndarray, H: np.ndarray | None, size: tuple[int, int]):
    """Warp ``frame`` into the reference frame using homography ``H``.

    ``size`` is (width, height) of the output.  If no calibration has been
    loaded the frame is returned untouched so the dashboard still runs.
    """
    if H is None:
        return frame
    return cv2.warpPerspective(
        frame, H, size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def isolate_nir(noir_bgr: np.ndarray, rgb_bgr: np.ndarray, k: float = 1.0):
    """Return (NIR estimate, reference red) as float32 arrays of equal shape.

    Shapes are harmonised by centre-cropping to the smaller overlap; the two
    sensors rarely share a resolution or an aspect ratio.
    """
    a, b = _crop_pair(noir_bgr, rgb_bgr)
    red_usb = b[..., 2].astype(np.float32)
    red_noir = a[..., 2].astype(np.float32)
    nir = np.maximum(red_noir - k * red_usb, 0.0)
    return nir, red_usb


def ndvi(noir_bgr: np.ndarray, rgb_bgr: np.ndarray, k: float = 1.0) -> np.ndarray:
    """Pixel-wise NDVI in [-1, +1], float32.

    Regions where the subtraction clipped to 0 report NDVI = -1.  That is a
    *calibration or lighting failure*, not a measurement -- callers should
    surface ``nir_valid_mask`` when they need to distinguish the two.
    """
    nir, red_usb = isolate_nir(noir_bgr, rgb_bgr, k)
    return (nir - red_usb) / (nir + red_usb + EPS)


def nir_valid_mask(noir_bgr: np.ndarray, rgb_bgr: np.ndarray, k: float = 1.0) -> np.ndarray:
    """Boolean mask of pixels where the NIR subtraction did *not* clip.

    A mostly-empty mask means ``k`` is too high or there is no NIR in the
    scene (indoor LED lighting emits essentially no NIR beyond 750 nm).
    """
    nir, _ = isolate_nir(noir_bgr, rgb_bgr, k)
    return nir > 0.0


def to_u8(ndvi_map: np.ndarray, window: tuple[float, float] = DEFAULT_WINDOW) -> np.ndarray:
    """Map NDVI through ``window`` onto [0, 255] as uint8."""
    lo, hi = window
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        raise ValueError('window must contain finite increasing bounds')
    scaled = (ndvi_map - lo) / (hi - lo)
    return (np.clip(scaled, 0.0, 1.0) * 255.0).round().astype(np.uint8)


def colorize(ndvi_map: np.ndarray, window: tuple[float, float] = DEFAULT_WINDOW) -> np.ndarray:
    """False-colour NDVI heatmap as a BGR uint8 image."""
    return cv2.applyColorMap(to_u8(ndvi_map, window), cv2.COLORMAP_JET)


# (label, representative NDVI, operator-facing description)
BANDS = (
    ("< 0.1", 0.00, "Low index (interpret with caution)"),
    ("0.1 - 0.2", 0.15, "Low positive index"),
    ("0.2 - 0.4", 0.30, "Intermediate index"),
    ("0.4 - 0.5", 0.45, "Higher index"),
    ("> 0.5", 0.70, "High index (vegetation candidate)"),
)


def _hex_for(value: float, window: tuple[float, float]) -> str:
    """Sample the *actual* render path for one NDVI value -> '#rrggbb'."""
    probe = np.array([[value]], dtype=np.float32)
    idx = to_u8(probe, window)
    b, g, r = cv2.applyColorMap(idx, cv2.COLORMAP_JET)[0, 0]
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def legend(window: tuple[float, float] = DEFAULT_WINDOW):
    """Legend swatches sampled from the same mapping the renderer uses.

    Building the key from the render path means it can never drift out of
    sync with the image -- the classic way a dashboard starts lying.
    """
    return [
        {"range": label, "desc": desc, "ndvi": value, "color": _hex_for(value, window)}
        for label, value, desc in BANDS
    ]


def _crop_pair(a: np.ndarray, b: np.ndarray):
    """Centre-crop both frames to the common smaller rectangle."""
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    if (a.shape[0], a.shape[1]) != (h, w):
        y = (a.shape[0] - h) // 2
        x = (a.shape[1] - w) // 2
        a = a[y:y + h, x:x + w]
    if (b.shape[0], b.shape[1]) != (h, w):
        y = (b.shape[0] - h) // 2
        x = (b.shape[1] - w) // 2
        b = b[y:y + h, x:x + w]
    return a, b


def null_map(shape: tuple[int, int]) -> np.ndarray:
    """A neutral placeholder NDVI field, used when only one sensor is live."""
    return np.zeros(shape[:2], dtype=np.float32)
