import io
import time
import unittest
from unittest.mock import patch
import calibrate
import cv2
import numpy as np
from app import Pipeline, build_app, load_homography
from calibrate import match_pair, reprojection_error


class FakeSensor:
    instances = []
    def __init__(self, source, name, size):
        if str(source) == 'missing':
            raise RuntimeError('missing test sensor')
        self.frame = np.full((48,64,3), 80 if name == 'RGB' else 160, np.uint8)
        self.reads = 0
        self.released = False
        self.instances.append(self)
    def read(self):
        self.reads += 1
        return self.frame
    def release(self):
        self.released = True


class AppTests(unittest.TestCase):
    def make_pipeline(self, **kwargs):
        p = Pipeline(size=(64,48), sensor_factory=FakeSensor, **kwargs)
        self.addCleanup(p.stop)
        return p

    def test_zero_one_two_and_uncalibrated_states(self):
        for rgb, noir, expected in [('missing','missing','NO SENSORS'),
                                     ('0','missing','SINGLE SENSOR'),
                                     ('missing','1','SINGLE SENSOR'),
                                     ('0','0','SINGLE SENSOR'),
                                     ('0','1','NOT CALIBRATED')]:
            with self.subTest(expected=expected, rgb=rgb):
                p = self.make_pipeline(rgb_src=rgb, noir_src=noir)
                p.process_once()
                s = p.state()
                self.assertEqual(s['status'], expected)
                self.assertFalse(s['ndvi_online'])
                self.assertIsNone(s['mean_ndvi'])

    def test_online_disconnect_and_stale(self):
        p = self.make_pipeline(H=np.eye(3))
        p.process_once()
        self.assertTrue(p.state()['ndvi_online'])
        p.noir.frame = None
        p.process_once()
        self.assertEqual(p.state()['status'], 'SINGLE SENSOR')
        self.assertIsNone(p.state()['mean_ndvi'])
        p._last_update = time.monotonic()-3
        self.assertEqual(p.state()['status'], 'NO SENSORS')

    def test_simulation_api_and_all_streams(self):
        p = self.make_pipeline(demo=True)
        p.process_once()
        client = build_app(p).test_client()
        self.assertEqual(client.get('/').status_code, 200)
        s = client.get('/api/state').get_json()
        self.assertEqual(s['status'], 'SIMULATION')
        self.assertFalse(s['ndvi_online'])
        self.assertFalse(s['calibrated'])
        for key in ('rgb', 'noir', 'ndvi'):
            response = client.get('/video/'+key, buffered=False)
            chunk = next(iter(response.response))
            payload = chunk.split(b'\r\n\r\n',1)[1][:-2]
            self.assertIsNotNone(cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR))
            response.close()
        self.assertEqual(client.get('/video/bogus').status_code, 404)

    def test_clients_use_same_cached_batch_without_capture(self):
        p = self.make_pipeline(H=np.eye(3))
        p.process_once()
        for key in ('rgb','noir','ndvi'):
            stream = p.stream(key)
            next(stream)
            stream.close()
        self.assertEqual(p.rgb.reads, 1)
        self.assertEqual(p.noir.reads, 1)

    def test_warp_border_excluded(self):
        H = np.array([[1,0,16],[0,1,0],[0,0,1]],float)
        p = self.make_pipeline(H=H)
        p.process_once()
        self.assertAlmostEqual(p.state()['valid_fraction'], .75)
        self.assertAlmostEqual(p.state()['mean_ndvi'], 0.)

    def test_invalid_inputs_and_calibration_file(self):
        for kwargs in ({'gain':float('nan')}, {'window':(1,1)}, {'H':np.zeros((3,3))}):
            with self.assertRaises(ValueError):
                self.make_pipeline(**kwargs)
        self.assertIsNone(load_homography(io.BytesIO(b'invalid')))
        file = io.BytesIO()
        np.save(file, np.eye(3))
        file.seek(0)
        np.testing.assert_array_equal(load_homography(file), np.eye(3))
        file = io.BytesIO()
        np.save(file, np.full((3,3), np.nan))
        file.seek(0)
        self.assertIsNone(load_homography(file))

    def test_worker_stops_and_releases(self):
        p = self.make_pipeline(H=np.eye(3)).start()
        with p._condition:
            ready = p._condition.wait_for(lambda: p._sequence > 0, timeout=3)
        self.assertTrue(ready)
        p.stop()
        self.assertFalse(p._thread.is_alive())
        self.assertTrue(p.rgb.released)
        self.assertTrue(p.noir.released)


class CalibrationTests(unittest.TestCase):
    def test_integer_ransac_mask_selects_actual_inliers(self):
        src = np.array([[[0,0]],[[10,0]],[[10,10]],[[0,10]],[[50,50]]],np.float32)
        H = np.array([[1,0,3],[0,1,2],[0,0,1]],float)
        dst = cv2.perspectiveTransform(src,H)
        dst[-1] += 100
        mask = np.array([[1],[1],[1],[1],[0]],np.uint8)
        self.assertAlmostEqual(reprojection_error(src,dst,H,mask),0.)

    def test_empty_inliers_rejected(self):
        pts = np.zeros((4,1,2), np.float32)
        with self.assertRaises(ValueError):
            reprojection_error(pts,pts,np.eye(3),np.zeros((4,1),np.uint8))

    def test_textured_pair_recovers_translation(self):
        rng = np.random.default_rng(42)
        gray = rng.integers(0,256,(240,320),dtype=np.uint8)
        noir = cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
        expected = np.array([[1,0,8],[0,1,5],[0,0,1]],float)
        rgb = cv2.warpPerspective(noir,expected,(320,240))
        src,dst = match_pair(noir,rgb,cv2.ORB_create(nfeatures=1500),cv2.BFMatcher(cv2.NORM_HAMMING))
        self.assertIsNotNone(src)
        H,mask = cv2.findHomography(src,dst,cv2.RANSAC,3.)
        self.assertLess(reprojection_error(src,dst,H,mask),1.)
        probes = np.array([[[80,80]],[[200,150]]],np.float32)
        np.testing.assert_allclose(cv2.perspectiveTransform(probes,H),
                                   cv2.perspectiveTransform(probes,expected),atol=1.)

    def test_calibration_cli_saves_a_valid_fit_and_releases_captures(self):
        rng = np.random.default_rng(19)
        image = cv2.cvtColor(rng.integers(0,256,(240,320),dtype=np.uint8),cv2.COLOR_GRAY2BGR)
        expected = np.array([[1,0,8],[0,1,5],[0,0,1]],float)
        class Capture:
            def __init__(self, frame):
                self.frame, self.released = frame, False
            def read(self):
                return self.frame
            def release(self):
                self.released = True
        noir = Capture(image)
        rgb = Capture(cv2.warpPerspective(image,expected,(320,240)))
        with patch('sys.argv', ['calibrate.py','--pairs','4','--width','320','--height','240']), \
             patch('calibrate.open_capture', side_effect=[noir,rgb]), \
             patch('calibrate.time.sleep'), patch('calibrate.np.save') as save:
            self.assertEqual(calibrate.main(),0)
        self.assertTrue(noir.released and rgb.released)
        save.assert_called_once()
        H = save.call_args.args[1]
        probes = np.array([[[80,80]],[[200,150]]],np.float32)
        np.testing.assert_allclose(cv2.perspectiveTransform(probes,H),
                                   cv2.perspectiveTransform(probes,expected),atol=1.)

    def test_blank_target_has_no_features(self):
        image = np.zeros((48,64,3), np.uint8)
        self.assertEqual(match_pair(image,image,cv2.ORB_create(),cv2.BFMatcher(cv2.NORM_HAMMING)),
                         (None,None))


if __name__ == '__main__':
    unittest.main()
