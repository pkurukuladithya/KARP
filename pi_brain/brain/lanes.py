"""
Fast classical lane detection for the Pi (no neural network).

  crop road ROI -> downscale to `work_width` -> white/yellow paint mask + Canny edges
  -> trapezoid mask -> probabilistic Hough -> split by slope into left/right
  -> weighted line fit x = a*y + b -> plausibility checks -> temporal smoothing

Runs in a few milliseconds at 320 px wide, so it can process every camera frame.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

Line = Tuple[float, float]  # x = a*y + b, in full-frame pixels


@dataclass
class LaneResult:
    left: Optional[Line] = None
    right: Optional[Line] = None
    y_top: int = 0
    y_bottom: int = 0
    offset_ratio: float = 0.0  # car centre vs lane centre, in half-lane-widths (+ = car is right of centre)
    departure: str = "NONE"  # NONE | LEFT | RIGHT
    stable: bool = False  # both lines seen for several consecutive frames

    @property
    def both(self) -> bool:
        return self.left is not None and self.right is not None

    @staticmethod
    def x_at(line: Line, y: float) -> float:
        return line[0] * y + line[1]


class _SideState:
    def __init__(self) -> None:
        self.line: Optional[np.ndarray] = None  # (x_top, x_bottom)
        self.missed = 0


class LaneDetector:
    def __init__(self, cfg: dict):
        self.work_w = int(cfg.get("work_width", 320))
        self.roi_top = float(cfg.get("roi_top", 0.58))
        self.top_w = float(cfg.get("roi_top_width", 0.30))
        self.bot_w = float(cfg.get("roi_bottom_width", 1.0))
        self.hold = int(cfg.get("hold_frames", 6))
        self.dep_ratio = float(cfg.get("departure_ratio", 0.40))
        self._left, self._right = _SideState(), _SideState()
        self._both_streak = 0
        self._mask_key = None
        self._mask: Optional[np.ndarray] = None
        self._frame_w = 640

    def _roi_mask(self, h: int, w: int) -> np.ndarray:
        if self._mask_key != (h, w):
            m = np.zeros((h, w), np.uint8)
            cx = w / 2.0
            poly = np.array(
                [
                    (cx - w * self.bot_w / 2, h),
                    (cx - w * self.top_w / 2, 0),
                    (cx + w * self.top_w / 2, 0),
                    (cx + w * self.bot_w / 2, h),
                ],
                np.int32,
            )
            cv2.fillPoly(m, [poly], 255)
            self._mask, self._mask_key = m, (h, w)
        return self._mask

    def process(self, frame: np.ndarray) -> LaneResult:
        H, W = frame.shape[:2]
        self._frame_w = W
        y0 = int(H * self.roi_top)
        scale = W / float(self.work_w)
        roi = cv2.resize(frame[y0:H], (self.work_w, max(8, int(round((H - y0) / scale)))), interpolation=cv2.INTER_AREA)
        h, w = roi.shape[:2]

        # Paint mask (white + yellow) and edges, both limited to the road trapezoid
        hls = cv2.cvtColor(roi, cv2.COLOR_BGR2HLS)
        light = int(np.clip(np.percentile(hls[..., 1], 90) + 10, 150, 230))  # adapt to scene brightness
        white = cv2.inRange(hls, (0, light, 0), (180, 255, 255))
        yellow = cv2.inRange(hls, (12, 70, 80), (38, 230, 255))
        paint = cv2.bitwise_or(white, yellow)
        gray = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        edges = cv2.Canny(gray, 60, 150)
        # Keep edges that lie on/next to paint; plus pure paint boundaries
        paint_d = cv2.dilate(paint, np.ones((5, 5), np.uint8))
        feat = cv2.bitwise_and(edges, paint_d)
        if cv2.countNonZero(feat) < 30:  # faded paint / grey scene: fall back to all edges
            feat = edges
        feat = cv2.bitwise_and(feat, self._roi_mask(h, w))

        segs = cv2.HoughLinesP(
            feat, 1, np.pi / 180, threshold=18, minLineLength=max(8, w // 16), maxLineGap=max(6, w // 20)
        )
        left_fit = right_fit = None
        if segs is not None:
            s = segs.reshape(-1, 4).astype(np.float32)
            dx, dy = s[:, 2] - s[:, 0], s[:, 3] - s[:, 1]
            ok = np.abs(dx) > 1e-3
            slope = np.where(ok, dy / np.where(ok, dx, 1), 1e6)
            length = np.hypot(dx, dy)
            mid_x = (s[:, 0] + s[:, 2]) / 2
            left_sel = (slope < -0.35) & (slope > -5) & (mid_x < w * 0.6)
            right_sel = (slope > 0.35) & (slope < 5) & (mid_x > w * 0.4)
            left_fit = self._fit(s[left_sel], length[left_sel])
            right_fit = self._fit(s[right_sel], length[right_sel])

        # Convert fits to (x_top, x_bottom) in full-frame pixels
        def to_frame(fit):
            if fit is None:
                return None
            a, b = fit
            return np.array([(a * 0 + b) * scale, (a * h + b) * scale], np.float32)

        l_new, r_new = to_frame(left_fit), to_frame(right_fit)
        if l_new is not None and r_new is not None and not self._plausible(l_new, r_new, W):
            l_new = r_new = None  # inconsistent pair (e.g. random edges indoors)
        self._smooth(self._left, l_new)
        self._smooth(self._right, r_new)

        res = LaneResult(y_top=y0, y_bottom=H)
        span = float(H - y0)
        for side, attr in ((self._left, "left"), (self._right, "right")):
            if side.line is not None:
                xt, xb = side.line
                a = (xb - xt) / span
                setattr(res, attr, (float(a), float(xt - a * y0)))

        if res.both and self._plausible(self._left.line, self._right.line, W):
            self._both_streak += 1
        else:
            self._both_streak = 0
        res.stable = self._both_streak >= 4
        if res.both:
            xl, xr = LaneResult.x_at(res.left, H), LaneResult.x_at(res.right, H)
            half = max(1.0, (xr - xl) / 2)
            res.offset_ratio = float((W / 2.0 - (xl + xr) / 2.0) / half)
            if res.stable:
                if res.offset_ratio > self.dep_ratio:
                    res.departure = "RIGHT"
                elif res.offset_ratio < -self.dep_ratio:
                    res.departure = "LEFT"
        return res

    @staticmethod
    def _fit(segs: np.ndarray, weights: np.ndarray) -> Optional[Tuple[float, float]]:
        if len(segs) == 0 or weights.sum() < 15:
            return None
        ys = np.concatenate([segs[:, 1], segs[:, 3]])
        xs = np.concatenate([segs[:, 0], segs[:, 2]])
        wts = np.concatenate([weights, weights])
        if np.ptp(ys) < 4:
            return None
        a, b = np.polyfit(ys, xs, 1, w=np.sqrt(wts))
        return float(a), float(b)

    @staticmethod
    def _plausible(left: np.ndarray, right: np.ndarray, W: int) -> bool:
        top_gap, bot_gap = right[0] - left[0], right[1] - left[1]
        return (0.25 * W < bot_gap < 1.6 * W) and (-0.02 * W < top_gap < bot_gap * 0.85)

    def _smooth(self, st: _SideState, new: Optional[np.ndarray]) -> None:
        if new is None:
            st.missed += 1
            if st.missed > self.hold:
                st.line = None
            return
        if st.line is not None and np.max(np.abs(new - st.line)) > 0.2 * self._frame_w:
            st.line = None  # big jump -> restart instead of averaging two different lines
        st.line = new if st.line is None else 0.6 * st.line + 0.4 * new
        st.missed = 0
