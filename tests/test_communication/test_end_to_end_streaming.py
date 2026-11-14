import time
import unittest
import numpy as np
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from laptop_vision.camera_receiver.stream_receiver import CameraStreamReceiver
from laptop_vision.video_encoder.stream_broadcaster import StreamBroadcaster
from raspberry_pi.video_streaming.rpi_stream_sender import RpiStreamSender
from raspberry_pi.ai_receiver.stream_receiver import RpiStreamReceiver


class TestEndToEndStreaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure a QCoreApplication instance exists for Qt signals
        cls.app = QCoreApplication.instance()
        if cls.app is None:
            cls.app = QCoreApplication([])

    def test_bidirectional_video_loop(self):
        port_a = 5910  # Pi -> Laptop
        port_b = 5911  # Laptop -> Pi

        # 1. Start Laptop Camera Receiver (port_a)
        laptop_rx = CameraStreamReceiver(host="127.0.0.1", port=port_a)
        laptop_rx.start()

        # 2. Start Pi Return Receiver (port_b)
        pi_rx = RpiStreamReceiver(listen_ip="127.0.0.1", listen_port=port_b)
        received_qimages = []
        pi_rx.frame_received.connect(lambda img, fps, lat: received_qimages.append(img))
        pi_rx.start()

        time.sleep(0.5)

        # 3. Start Pi Stream Sender (Direction A: Pi -> Laptop)
        pi_tx = RpiStreamSender(laptop_ip="127.0.0.1", port=port_a)
        pi_tx.start()

        # 4. Start Laptop Stream Broadcaster (Direction B: Laptop -> Pi)
        laptop_tx = StreamBroadcaster(target_ip="127.0.0.1", port=port_b)
        laptop_tx.start()

        time.sleep(1.0)

        # 5. Push mock frame through Direction A
        mock_frame = np.full((360, 640, 3), 120, dtype=np.uint8)
        ts_now = int(time.time() * 1000)
        pi_tx.push_frame(mock_frame, frame_id=1, timestamp_ms=ts_now)

        # 6. Retrieve on Laptop
        frame_tuple = laptop_rx.get_latest_frame(timeout=2.0)
        self.assertIsNotNone(frame_tuple)
        rx_frame, frame_id, rx_ts = frame_tuple
        self.assertEqual(frame_id, 1)
        self.assertEqual(rx_frame.shape, (360, 640, 3))

        # 7. Push annotated frame through Direction B (Laptop -> Pi)
        annotated_frame = rx_frame.copy()
        laptop_tx.broadcast_frame(annotated_frame, frame_id=1, timestamp_ms=rx_ts)

        # Wait for Pi to receive
        deadline = time.time() + 2.0
        while not received_qimages and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.05)

        self.assertGreater(len(received_qimages), 0)
        qimg = received_qimages[0]
        self.assertEqual(qimg.width(), 640)
        self.assertEqual(qimg.height(), 360)

        # 8. Clean Teardown
        pi_tx.stop()
        laptop_tx.stop()
        laptop_rx.stop()
        pi_rx.stop()


if __name__ == "__main__":
    unittest.main()
