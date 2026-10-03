"""Deterministic synthetic sensor pairs; these are not physical measurements."""
import cv2
import numpy as np


def frame_pair(size=(640, 480)):
    w, h = size
    rgb = np.zeros((h, w, 3), np.uint8)
    noir = np.zeros_like(rgb)
    # For k=1: NIR=NoIR_red-RGB_red. Known indices: .75, 0, -.5.
    bands = [('HIGH NIR', 20, 160), ('NEUTRAL', 60, 120), ('LOW NIR', 90, 120)]
    for i, (label, red, mixed) in enumerate(bands):
        x0, x1 = i*w//3, (i+1)*w//3
        rgb[:, x0:x1] = (red, red, red)
        noir[:, x0:x1] = (mixed, mixed, mixed)
        for frame in (rgb, noir):
            cv2.putText(frame, label, (x0+8, h//2), cv2.FONT_HERSHEY_SIMPLEX,
                        .5, (255, 255, 255), 1)
    return rgb, noir
