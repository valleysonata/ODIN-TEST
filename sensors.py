"""Capture adapters. Picamera2 is optional and only imported on Raspberry Pi."""
import cv2


def parse_source(value):
    return int(value) if str(value).isdigit() else str(value)


class Sensor:
    def __init__(self, source, name, size=(640, 480)):
        self.name = name
        self.cap = None
        self.picam = None
        try:
            if str(source).startswith('picamera2:'):
                from picamera2 import Picamera2
                self.picam = Picamera2(int(str(source).split(':', 1)[1]))
                # Picamera2 RGB888 arrays have BGR byte order, matching OpenCV.
                self.picam.configure(self.picam.create_video_configuration(
                    main={'size': size, 'format': 'RGB888'}))
                self.picam.start()
            else:
                self.cap = cv2.VideoCapture(parse_source(source))
                if not self.cap.isOpened():
                    raise RuntimeError(f'cannot open {name} source {source!r}')
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        except Exception:
            self.release()
            raise

    def read(self):
        if self.picam is not None:
            return self.picam.capture_array('main')
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self):
        if self.cap is not None:
            self.cap.release()
        if self.picam is not None:
            self.picam.close()
