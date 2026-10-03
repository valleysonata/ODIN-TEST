"""ODIN live dashboard.

Flask app that pulls two sensor feeds, registers the NoIR frame onto the USB
frame with a stored homography, isolates NIR by channel subtraction and
streams the false-colour NDVI result as MJPEG.

Two sensors are required for NDVI.  If only one can be opened the app still
runs and serves previews, but the NDVI output is replaced by an explicit
"OFFLINE" plate rather than a plausible-looking colour map -- a single camera
cannot produce a meaningful index and faking one would make the dashboard lie.

Usage
-----
    python app.py                       # --noir 1 --rgb 0
    python app.py --noir 0 --rgb 0      # single sensor -> NDVI offline
    python app.py --gain 1.25 --port 8080
"""
from __future__ import annotations

import argparse
import os
import threading
import time
from collections import deque

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request

import engine

HERE = os.path.dirname(os.path.abspath(__file__))


def _src(value: str):
    return int(value) if str(value).isdigit() else str(value)


class Sensor:
    """A single camera with a lock, so MJPEG readers cannot tear frames."""

    def __init__(self, source, name: str, size=(640, 480)):
        self.name = name
        self._lock = threading.Lock()
        cap = cv2.VideoCapture(source if isinstance(source, int) else str(source))
        if not cap.isOpened():
            raise RuntimeError(f"cannot open {name} source {source!r}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        self.cap = cap
        self.frames = 0
        self._stamp = time.monotonic()

    def read(self):
        with self._lock:
            ok, frame = self.cap.read()
        if not ok:
            return None
        self.frames += 1
        return frame

    @property
    def fps(self) -> float:
        now = time.monotonic()
        dt = now - self._stamp
        if dt < 1.0:
            return 0.0
        fps = self.frames / dt
        self.frames, self._stamp = 0, now
        return fps

    def release(self):
        self.cap.release()


class Pipeline:
    def __init__(self, rgb_src, noir_src, gain: float, window, H=None):
        self.k = gain
        self.window = window
        self.H = H
        self.mode = "single"
        self.rgb = Sensor(_src(rgb_src), "RGB")
        self.noir = None
        if str(noir_src) != str(rgb_src):
            try:
                self.noir = Sensor(_src(noir_src), "NoIR")
            except RuntimeError as exc:
                print(f"[odin] {exc}; running single-sensor (NDVI offline)")
        if self.noir is not None:
            self.mode = "dual"
        self._history = deque(maxlen=100)
        self._mean = None

    @property
    def calibrated(self) -> bool:
        return self.H is not None

    @property
    def ndvi_online(self) -> bool:
        return self.mode == "dual"

    @property
    def fps(self) -> float:
        """Rough pipeline rate: seconds between completed frame batches."""
        if len(self._history) < 2:
            return 0.0
        span = self._history[-1] - self._history[0]
        if span <= 0:
            return 0.0
        return (len(self._history) - 1) / span

    def state(self) -> dict:
        return {
            "mode": self.mode,
            "ndvi_online": self.ndvi_online,
            "calibrated": self.calibrated,
            "k": round(self.k, 3),
            "window": [round(v, 2) for v in self.window],
            "mean_ndvi": None if self._mean is None else round(float(self._mean), 3),
            "legend": engine.legend(self.window),
        }

    def frames(self):
        """Yield (rgb, noir, ndvi_bgr) or (rgb, None, None) in single mode."""
        rgb = self.rgb.read()
        if rgb is None:
            time.sleep(0.02)
            return None, None, None
        if self.noir is None:
            return rgb, None, None
        noir = self.noir.read()
        if noir is None:
            time.sleep(0.02)
            return rgb, None, None

        aligned = engine.align(noir, self.H, (rgb.shape[1], rgb.shape[0]))
        ndvi_map = engine.ndvi(aligned, rgb, self.k)
        self._mean = float(np.nanmean(ndvi_map))
        self._history.append(time.monotonic())
        return rgb, aligned, engine.colorize(ndvi_map, self.window)


def _plate(text: str, shape, color=(40, 46, 60)) -> np.ndarray:
    img = np.full(shape, color, dtype=np.uint8)
    cv2.putText(img, text, (24, shape[0] // 2), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (246, 194, 118), 2, cv2.LINE_AA)
    return img


def _mjpeg(frame, quality=80):
    ok, buf = cv2.imencode(".jpg", frame,
                           [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else b""


def build_app(pipeline: Pipeline) -> Flask:
    app = Flask(__name__)

    def generator(pick, offline_text="NDVI OFFLINE"):
        while True:
            rgb, noir, ndvi = pipeline.frames()
            if rgb is None:
                continue
            frame = pick(rgb, noir, ndvi)
            if frame is None:
                frame = _plate(offline_text, rgb.shape)
            payload = _mjpeg(frame)
            if payload:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + payload + b"\r\n")
            time.sleep(0.01)

    @app.route("/")
    def index():
        return render_template("index.html", state=pipeline.state())

    @app.route("/api/state")
    def api_state():
        return jsonify(pipeline.state())

    @app.route("/video/ndvi")
    def video_ndvi():
        return Response(
            generator(lambda r, n, d: d, "NDVI OFFLINE - NEED 2 SENSORS"),
            mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/video/rgb")
    def video_rgb():
        return Response(generator(lambda r, n, d: r),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/video/noir")
    def video_noir():
        return Response(
            generator(lambda r, n, d: n, "NOIR OFFLINE"),
            mimetype="multipart/x-mixed-replace; boundary=frame")

    return app


def load_homography(path: str):
    if not os.path.exists(path):
        print(f"[odin] no {path} -- run `python calibrate.py` first. "
              f"Streams will be unregistered.")
        return None
    H = np.load(path)
    if H.shape != (3, 3):
        print(f"[odin] {path} has shape {H.shape}, expected (3, 3); ignoring.")
        return None
    return H


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rgb", default="0", help="USB webcam index / path / URL")
    ap.add_argument("--noir", default="1", help="NoIR camera index / path / URL")
    ap.add_argument("--gain", type=float, default=float(os.environ.get("ODIN_K", "1.0")),
                    help="radiometric gain k (tune against a grey card)")
    ap.add_argument("--window", default="-0.2,1.0",
                    help="NDVI->colour window as lo,hi (default -0.2,1.0)")
    ap.add_argument("--homography", default=os.path.join(HERE, "matrix_h.npy"))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    lo, hi = (float(x) for x in args.window.split(","))
    pipeline = Pipeline(args.rgb, args.noir, args.gain, (lo, hi),
                        H=load_homography(args.homography))

    print(f"[odin] mode      : {pipeline.mode}")
    print(f"[odin] NDVI      : {'ONLINE' if pipeline.ndvi_online else 'OFFLINE'}")
    print(f"[odin] calibrated: {'yes' if pipeline.calibrated else 'NO'}")
    print(f"[odin] k         : {pipeline.k}")
    print(f"[odin] window    : {pipeline.window}")
    if pipeline.ndvi_online and not pipeline.calibrated:
        print("[odin] WARNING: sensors are NOT registered. NDVI will be")
        print("[odin] computed on misaligned frames -- fine for a smoke test,")
        print("[odin] useless for a reading. Run `python calibrate.py`.")

    app = build_app(pipeline)
    app.run(host=args.host, port=args.port, threaded=True,
            debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
