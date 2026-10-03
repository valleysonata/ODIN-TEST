"""ODIN experimental spectral dashboard. Run --demo without cameras."""
from __future__ import annotations
import argparse
from collections import deque
import logging
import os
import threading
import time
import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template
import engine
from sensors import Sensor, parse_source
from simulation import frame_pair

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = logging.getLogger('odin')


def valid_homography(H):
    try:
        H = np.asarray(H, dtype=np.float64)
        return H.shape == (3, 3) and np.isfinite(H).all() and np.linalg.matrix_rank(H) == 3
    except (ValueError, TypeError, np.linalg.LinAlgError):
        return False


def load_homography(path):
    try:
        H = np.load(path, allow_pickle=False)
        if not valid_homography(H):
            raise ValueError('expected a finite, nonsingular 3x3 matrix')
        return H
    except (OSError, ValueError, EOFError) as exc:
        LOG.warning('Calibration unavailable: %s', exc)
        return None


def _plate(text, shape=(480, 640, 3)):
    img = np.full(shape, (40, 46, 60), np.uint8)
    cv2.putText(img, text, (16, shape[0]//2), cv2.FONT_HERSHEY_SIMPLEX,
                .6, (246, 194, 118), 1, cv2.LINE_AA)
    return img


def _mjpeg(frame):
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError('JPEG encoding failed')
    return buf.tobytes()


class Pipeline:
    """One producer owns captures; all HTTP clients consume cached JPEG batches."""
    def __init__(self, rgb_src='0', noir_src='1', gain=1., window=(-.2, 1.), H=None,
                 demo=False, size=(640, 480), target_fps=30, sensor_factory=Sensor):
        if not np.isfinite(gain) or gain <= 0:
            raise ValueError('gain must be finite and positive')
        if len(window) != 2 or not np.isfinite(window).all() or window[0] >= window[1]:
            raise ValueError('window must contain two finite increasing values')
        if H is not None and not valid_homography(H):
            raise ValueError('invalid homography')
        if min(size) < 32 or not np.isfinite(target_fps) or target_fps <= 0:
            raise ValueError('invalid size or target FPS')
        self.k, self.window, self.H = gain, window, H
        self.demo, self.size, self.target_fps = demo, size, target_fps
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = None
        self._sequence = 0
        self._history = deque(maxlen=100)
        self._last_update = 0.
        self._jpeg = {}
        self._mean = self._valid_fraction = self._nir_positive_fraction = None
        self._healthy = {'rgb': False, 'noir': False}
        self.errors = {}
        self.rgb = self.noir = None
        if not demo:
            for key, source in (('rgb', rgb_src), ('noir', noir_src)):
                if key == 'noir' and parse_source(source) == parse_source(rgb_src):
                    self.errors[key] = 'same source as RGB; second capture disabled'
                    continue
                try:
                    setattr(self, key, sensor_factory(source, key.upper(), size))
                except Exception as exc:
                    self.errors[key] = str(exc)
                    LOG.warning('%s unavailable: %s', key, exc)

    def _status(self):
        fresh = time.monotonic() - self._last_update < 2.
        count = sum(self._healthy.values()) if fresh else 0
        if 'pipeline' in self.errors:
            return 'PROCESSING ERROR'
        if self.demo:
            return 'SIMULATION' if fresh else 'STARTING'
        if count == 0:
            return 'NO SENSORS'
        if count == 1:
            return 'SINGLE SENSOR'
        return 'NDVI ONLINE' if self.H is not None else 'NOT CALIBRATED'

    def state(self):
        with self._condition:
            status = self._status()
            online = status == 'NDVI ONLINE'
            active = online or status == 'SIMULATION'
            span = self._history[-1] - self._history[0] if len(self._history) > 1 else 0
            return {'status': status, 'mode': 'simulation' if self.demo else
                    ('dual' if sum(self._healthy.values()) == 2 else 'single' if
                     sum(self._healthy.values()) == 1 else 'none'),
                    'simulation': self.demo, 'ndvi_online': online,
                    'calibrated': self.H is not None and not self.demo,
                    'k': self.k, 'window': list(self.window),
                    'mean_ndvi': self._mean if active else None,
                    'valid_fraction': self._valid_fraction if active else None,
                    'nir_positive_fraction': self._nir_positive_fraction if active else None,
                    'fps': round((len(self._history)-1)/span, 1) if span and active else 0.,
                    'sensors': dict(self._healthy) if time.monotonic()-self._last_update < 2 else
                               {'rgb': False, 'noir': False},
                    'errors': dict(self.errors), 'legend': engine.legend(self.window)}

    def process_once(self):
        errors = dict(self.errors)
        errors.pop('pipeline', None)
        if self.demo:
            rgb, noir = frame_pair(self.size)
        else:
            frames = []
            for key in ('rgb', 'noir'):
                sensor = getattr(self, key)
                try:
                    frame = sensor.read() if sensor is not None else None
                    if sensor is not None:
                        if frame is None:
                            errors[key] = 'capture returned no frame'
                        else:
                            errors.pop(key, None)
                except Exception as exc:
                    frame = None
                    errors[key] = str(exc)
                frames.append(frame)
            rgb, noir = frames
        healthy = {'rgb': rgb is not None, 'noir': noir is not None}
        heat = None
        mean = valid_fraction = positive_fraction = None
        if rgb is not None and noir is not None and (self.demo or self.H is not None):
            H = np.eye(3) if self.demo else self.H
            size = (rgb.shape[1], rgb.shape[0])
            aligned = engine.align(noir, H, size)
            overlap = cv2.warpPerspective(np.ones(noir.shape[:2], np.uint8), H, size,
                                         flags=cv2.INTER_NEAREST) > 0
            nir, red = engine.isolate_nir(aligned, rgb, self.k)
            # Exclude warp borders, black signal and saturated red channels.
            valid = overlap & (nir+red > 1.) & (aligned[..., 2] < 250) & (rgb[..., 2] < 250)
            values = (nir-red)/(nir+red+engine.EPS)
            heat = engine.colorize(values, self.window)
            heat[~valid] = (40, 46, 60)
            valid_fraction = float(valid.mean())
            positive_fraction = float((nir[valid] > 0).mean()) if valid.any() else 0.
            mean = float(values[valid].mean()) if valid.any() else None
        count = sum(healthy.values())
        reason = 'NOT CALIBRATED' if count == 2 else 'NEED TWO HEALTHY SENSORS'
        output = {'rgb': rgb if rgb is not None else _plate('RGB OFFLINE'),
                  'noir': noir if noir is not None else _plate('NOIR OFFLINE'),
                  'ndvi': heat if heat is not None else _plate(reason)}
        if self.demo:
            for frame in output.values():
                cv2.putText(frame, 'Demo', (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX, .45, (255,255,255), 1)
        jpeg = {key: _mjpeg(frame) for key, frame in output.items()}
        with self._condition:
            self._healthy, self.errors = healthy, errors
            self._mean, self._valid_fraction = mean, valid_fraction
            self._nir_positive_fraction = positive_fraction
            self._last_update = time.monotonic()
            self._history.append(self._last_update)
            self._jpeg = jpeg
            self._sequence += 1
            self._condition.notify_all()

    def _run(self):
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    self.process_once()
                except Exception:
                    LOG.exception('Frame processing failed')
                    with self._condition:
                        self._healthy = {'rgb': False, 'noir': False}
                        self._mean = None
                        self.errors['pipeline'] = 'processing failed; see server log'
                        self._jpeg = {key: _mjpeg(_plate('PROCESSING ERROR'))
                                      for key in ('rgb', 'noir', 'ndvi')}
                        self._sequence += 1
                        self._condition.notify_all()
                self._stop.wait(max(0., 1/self.target_fps-(time.monotonic()-started)))
        finally:
            for sensor in (self.rgb, self.noir):
                if sensor is not None:
                    sensor.release()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='odin-capture', daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3)
        else:
            for sensor in (self.rgb, self.noir):
                if sensor is not None:
                    sensor.release()

    def stream(self, key):
        sequence = -1
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(lambda: self._sequence != sequence or self._stop.is_set(),
                                         timeout=2)
                if self._stop.is_set():
                    break
                sequence = self._sequence
                payload = self._jpeg.get(key)
                stale = time.monotonic()-self._last_update >= 2
            if stale:
                payload = _mjpeg(_plate('CAPTURE STALE / OFFLINE'))
            if payload:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+payload+b'\r\n'


def build_app(pipeline):
    app = Flask(__name__)
    @app.get('/')
    def index():
        return render_template('index.html', state=pipeline.state())
    @app.get('/api/state')
    def api_state():
        return jsonify(pipeline.state())
    @app.get('/video/<key>')
    def video(key):
        if key not in ('rgb', 'noir', 'ndvi'):
            return 'Unknown stream', 404
        return Response(pipeline.stream(key), mimetype='multipart/x-mixed-replace; boundary=frame',
                        headers={'Cache-Control': 'no-store'})
    return app


def main():
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--demo', action='store_true', help='labeled synthetic frames; no cameras')
    ap.add_argument('--rgb', default='0', help='OpenCV index/path/URL or picamera2:0')
    ap.add_argument('--noir', default='1', help='OpenCV index/path/URL or picamera2:0')
    ap.add_argument('--gain', '--k', type=float, default=os.environ.get('ODIN_K', '1'))
    ap.add_argument('--window', default='-0.2,1.0', help='use --window=-0.2,1.0')
    ap.add_argument('--homography', default=os.path.join(HERE, 'matrix_h.npy'))
    ap.add_argument('--width', type=int, default=640)
    ap.add_argument('--height', type=int, default=480)
    ap.add_argument('--fps', type=float, default=30, help='producer rate limit, not guaranteed FPS')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8080)
    args = ap.parse_args()
    try:
        window = tuple(float(x) for x in args.window.split(','))
        pipeline = Pipeline(args.rgb, args.noir, args.gain, window,
                            H=None if args.demo else load_homography(args.homography),
                            demo=args.demo, size=(args.width, args.height), target_fps=args.fps)
    except ValueError as exc:
        ap.error(str(exc))
    pipeline.start()
    try:
        build_app(pipeline).run(host=args.host, port=args.port, threaded=True,
                               debug=False, use_reloader=False)
    finally:
        pipeline.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
