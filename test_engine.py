import unittest
import numpy as np
import cv2
import engine


class EngineTests(unittest.TestCase):
    def test_known_indices_and_unsigned_subtraction(self):
        rgb = np.zeros((1, 4, 3), np.uint8)
        noir = np.zeros_like(rgb)
        rgb[0, :, 2] = [20, 60, 90, 200]
        noir[0, :, 2] = [160, 120, 120, 10]
        np.testing.assert_allclose(engine.ndvi(noir, rgb), [[.75, 0, -.5, -1]], atol=1e-6)
        np.testing.assert_array_equal(engine.nir_valid_mask(noir, rgb), [[True, True, True, False]])

    def test_black_is_finite(self):
        black = np.zeros((8, 8, 3), np.uint8)
        values = engine.ndvi(black, black)
        self.assertTrue(np.isfinite(values).all())
        np.testing.assert_array_equal(values, 0)

    def test_homography_direction(self):
        image = np.zeros((16, 16, 3), np.uint8)
        image[4, 5] = 255
        H = np.array([[1,0,3],[0,1,2],[0,0,1]], float)
        np.testing.assert_array_equal(engine.align(image, H, (16,16))[6,8], [255]*3)

    def test_crop_and_render(self):
        values = engine.ndvi(np.zeros((12,10,3), np.uint8), np.zeros((8,16,3), np.uint8))
        self.assertEqual(values.shape, (8,10))
        self.assertEqual(engine.colorize(values).shape, (8,10,3))
        self.assertEqual(engine.to_u8(np.array([[-2., 2.]])).tolist(), [[0,255]])

    def test_legend_matches_rendering(self):
        for band in engine.legend():
            b,g,r = engine.colorize(np.array([[band['ndvi']]], np.float32))[0,0]
            self.assertEqual(band['color'], f'#{r:02x}{g:02x}{b:02x}')
        with self.assertRaises(ValueError):
            engine.to_u8(np.zeros((1,1)), (1,1))


if __name__ == '__main__':
    unittest.main()
