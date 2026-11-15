"""
Optional MJPEG web view: open http://<pi-ip>:<port>/ on a phone or laptop.

Much lighter than VNC: frames are JPEG-encoded only while someone is watching,
at a capped rate, and the Pi's desktop is not re-encoded.
"""

from __future__ import annotations
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("pi_brain.web")

_PAGE = b"""<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>KARP Pi Brain</title><style>body{margin:0;background:#000;display:flex;justify-content:center}
img{max-width:100vw;max-height:100vh}</style></head><body><img src="/stream"></body></html>"""


class WebView:
    def __init__(self, port: int, fps: int = 12, quality: int = 70):
        self.port, self.fps, self.quality = port, max(1, fps), quality
        self._cond = threading.Condition()
        self._frame: Optional[np.ndarray] = None
        self._seq = 0
        self.clients = 0
        view = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence per-request logging
                pass

            def do_GET(self):
                if self.path.startswith("/stream"):
                    view._serve_stream(self)
                elif self.path.startswith("/snapshot"):
                    jpg = view._encode_latest()
                    if jpg is None:
                        self.send_error(503)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpg)))
                    self.end_headers()
                    self.wfile.write(jpg)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(_PAGE)

        self._server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="WebView")

    def start(self) -> None:
        self._thread.start()
        logger.info(f"Web view on http://<this-pi-ip>:{self.port}/")

    def stop(self) -> None:
        self._server.shutdown()

    def publish(self, frame: np.ndarray) -> None:
        # Only a reference is stored here; JPEG encoding happens in the viewer's thread,
        # so with nobody watching this costs nothing.
        with self._cond:
            self._frame = frame
            self._seq += 1
            self._cond.notify_all()

    def _encode_latest(self) -> Optional[bytes]:
        with self._cond:
            f = self._frame
        if f is None:
            return None
        ok, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
        return buf.tobytes() if ok else None

    def _serve_stream(self, h: BaseHTTPRequestHandler) -> None:
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        h.send_header("Cache-Control", "no-cache")
        h.end_headers()
        with self._cond:
            self.clients += 1
        last, period = -1, 1.0 / self.fps
        try:
            while True:
                t0 = time.perf_counter()
                with self._cond:
                    self._cond.wait_for(lambda: self._seq != last, timeout=2.0)
                    last = self._seq
                jpg = self._encode_latest()
                if jpg is None:
                    continue
                h.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
                h.wfile.write(jpg)
                h.wfile.write(b"\r\n")
                delay = period - (time.perf_counter() - t0)
                if delay > 0:
                    time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with self._cond:
                self.clients -= 1
