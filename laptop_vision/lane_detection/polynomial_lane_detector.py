"""
Robust 2nd-Degree Polynomial Sliding Window Lane Detector.
Computes Perspective IPM, HLS/LAB thresholding, lane curvature, and vehicle center offset.
"""

from __future__ import annotations
import math
from typing import List, Optional, Tuple
import cv2
import numpy as np

from shared.protocols.message_schemas import LaneData
from .lane_detector_base import LaneDetectorBase
from .departure_warning import DepartureWarningEvaluator


class PolynomialLaneDetector(LaneDetectorBase):
    def __init__(
        self,
        img_width: int = 1280,
        img_height: int = 720,
        work_width: int = 640,
    ):
        # Lane fitting runs at a reduced working resolution (results are scaled back),
        # which cuts CPU time ~2-3x with no practical loss for lane geometry.
        self.work_width = work_width
        self._in_size = (0, 0)
        self.ldw_evaluator = DepartureWarningEvaluator(departure_threshold_m=0.38)

        # Sliding window parameters (margin/minpix scaled with width in _setup_geometry)
        self.nwindows = 9
        self._setup_geometry(img_width, img_height)

        # Smoothing filter across consecutive frames
        self._prev_left_fit: Optional[np.ndarray] = None
        self._prev_right_fit: Optional[np.ndarray] = None

    def _setup_geometry(self, img_width: int, img_height: int) -> None:
        """(Re)computes perspective transforms and pixel scales for the given frame size."""
        self.img_w = img_width
        self.img_h = img_height
        self.ym_per_pix = 30.0 / img_height
        # Warped lane spans ~50% of the width (0.25w .. 0.75w) for a 3.7 m lane
        self.xm_per_pix = 3.7 / (0.5 * img_width)
        scale = img_width / 1280.0
        self.margin = max(40, int(100 * scale))
        self.minpix = max(20, int(50 * scale * scale))
        self.min_lane_px = max(60, int(150 * scale * scale))
        self.min_base_sep = int(200 * scale)

        self._src_pts = np.float32([
            [int(img_width * 0.18), img_height],
            [int(img_width * 0.44), int(img_height * 0.62)],
            [int(img_width * 0.56), int(img_height * 0.62)],
            [int(img_width * 0.82), img_height],
        ])
        self._dst_pts = np.float32([
            [int(img_width * 0.25), img_height],
            [int(img_width * 0.25), 0],
            [int(img_width * 0.75), 0],
            [int(img_width * 0.75), img_height],
        ])
        self.M = cv2.getPerspectiveTransform(self._src_pts, self._dst_pts)
        self.M_inv = cv2.getPerspectiveTransform(self._dst_pts, self._src_pts)
        self._prev_left_fit = None
        self._prev_right_fit = None

    def detect(self, frame_bgr: np.ndarray) -> LaneData:
        in_h, in_w = frame_bgr.shape[:2]
        if (in_w, in_h) != self._in_size:
            self._in_size = (in_w, in_h)
            ww = min(self.work_width, in_w)
            wh = int(round(in_h * ww / in_w))
            self._setup_geometry(ww, wh)
        if in_w != self.img_w:
            frame_bgr = cv2.resize(frame_bgr, (self.img_w, self.img_h), interpolation=cv2.INTER_AREA)
        sx = in_w / float(self.img_w)
        sy = in_h / float(self.img_h)

        # 1. Color & Gradient Thresholding
        binary_warped = self._preprocess_and_warp(frame_bgr)

        # 2. Histogram & Sliding Window Search
        left_fit, right_fit, confidence = self._fit_polynomial(binary_warped)

        if left_fit is None or right_fit is None:
            # Fallback to previous fit if available with reduced confidence
            if self._prev_left_fit is not None and self._prev_right_fit is not None:
                left_fit = self._prev_left_fit
                right_fit = self._prev_right_fit
                confidence = 0.40
            else:
                return LaneData(detected=False, confidence=0.0)

        # Exponential moving average smoothing
        if self._prev_left_fit is not None:
            left_fit = 0.75 * left_fit + 0.25 * self._prev_left_fit
            right_fit = 0.75 * right_fit + 0.25 * self._prev_right_fit

        self._prev_left_fit = left_fit
        self._prev_right_fit = right_fit

        # 3. Calculate Curvature and Vehicle Offset
        curvature_m = self._measure_curvature(left_fit, right_fit)
        vehicle_offset_m = self._calculate_vehicle_offset(left_fit, right_fit)

        # 4. Evaluate Departure Warning
        departure_warning, _ = self.ldw_evaluator.evaluate(vehicle_offset_m)

        # 5. Generate Perspective Projection Points
        left_pts, right_pts = self._generate_lane_points(left_fit, right_fit)
        if sx != 1.0 or sy != 1.0:
            left_pts = [(int(x * sx), int(y * sy)) for x, y in left_pts]
            right_pts = [(int(x * sx), int(y * sy)) for x, y in right_pts]

        return LaneData(
            detected=True,
            confidence=round(confidence, 2),
            curvature_m=round(curvature_m, 1),
            vehicle_offset_m=round(vehicle_offset_m, 2),
            departure_warning=departure_warning,
            left_lane_pts=left_pts,
            right_lane_pts=right_pts,
        )

    def _preprocess_and_warp(self, frame_bgr: np.ndarray) -> np.ndarray:
        """HLS-S / LAB-B colour + Sobel-X gradient thresholds, then bird's-eye warp (all OpenCV-vectorised)."""
        hls = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HLS)
        l_channel = hls[:, :, 1]
        s_channel = hls[:, :, 2]
        b_channel = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)[:, :, 2]  # yellow lines

        abs_sobelx = cv2.convertScaleAbs(cv2.Sobel(l_channel, cv2.CV_16S, 1, 0))
        max_sobel = max(1.0, float(cv2.minMaxLoc(abs_sobelx)[1]))
        scaled_sobel = cv2.convertScaleAbs(abs_sobelx, alpha=255.0 / max_sobel)
        sxbinary = cv2.inRange(scaled_sobel, 25, 120)

        color_binary = cv2.bitwise_or(cv2.inRange(s_channel, 100, 255), cv2.inRange(b_channel, 155, 255))
        combined = cv2.bitwise_or(sxbinary, color_binary)

        return cv2.warpPerspective(combined, self.M, (self.img_w, self.img_h), flags=cv2.INTER_LINEAR)

    def _fit_polynomial(self, binary_warped: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], float]:
        # Take histogram of bottom half
        histogram = np.sum(binary_warped[binary_warped.shape[0] // 2:, :], axis=0)
        midpoint = int(histogram.shape[0] // 2)
        leftx_base = np.argmax(histogram[:midpoint])
        rightx_base = np.argmax(histogram[midpoint:]) + midpoint

        # Check if peaks are distinct and plausible
        if leftx_base < 50 or rightx_base > (self.img_w - 50) or (rightx_base - leftx_base) < self.min_base_sep:
            return None, None, 0.0

        window_height = int(binary_warped.shape[0] // self.nwindows)
        nonzero = binary_warped.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])

        leftx_current = leftx_base
        rightx_current = rightx_base

        left_lane_inds = []
        right_lane_inds = []

        for window in range(self.nwindows):
            win_y_low = binary_warped.shape[0] - (window + 1) * window_height
            win_y_high = binary_warped.shape[0] - window * window_height
            win_xleft_low = leftx_current - self.margin
            win_xleft_high = leftx_current + self.margin
            win_xright_low = rightx_current - self.margin
            win_xright_high = rightx_current + self.margin

            good_left_inds = (
                (nonzeroy >= win_y_low)
                & (nonzeroy < win_y_high)
                & (nonzerox >= win_xleft_low)
                & (nonzerox < win_xleft_high)
            ).nonzero()[0]
            good_right_inds = (
                (nonzeroy >= win_y_low)
                & (nonzeroy < win_y_high)
                & (nonzerox >= win_xright_low)
                & (nonzerox < win_xright_high)
            ).nonzero()[0]

            left_lane_inds.append(good_left_inds)
            right_lane_inds.append(good_right_inds)

            if len(good_left_inds) > self.minpix:
                leftx_current = int(np.mean(nonzerox[good_left_inds]))
            if len(good_right_inds) > self.minpix:
                rightx_current = int(np.mean(nonzerox[good_right_inds]))

        left_lane_inds = np.concatenate(left_lane_inds)
        right_lane_inds = np.concatenate(right_lane_inds)

        if len(left_lane_inds) < self.min_lane_px or len(right_lane_inds) < self.min_lane_px:
            return None, None, 0.0

        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds]
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]

        try:
            left_fit = np.polyfit(lefty, leftx, 2)
            right_fit = np.polyfit(righty, rightx, 2)
            confidence = min(1.0, (len(left_lane_inds) + len(right_lane_inds)) / 3000.0)
            return left_fit, right_fit, confidence
        except Exception:
            return None, None, 0.0

    def _measure_curvature(self, left_fit: np.ndarray, right_fit: np.ndarray) -> float:
        y_eval = self.img_h
        # Convert to real world meters
        left_a = left_fit[0] * (self.xm_per_pix / (self.ym_per_pix ** 2))
        left_b = left_fit[1] * (self.xm_per_pix / self.ym_per_pix)
        denom_l = abs(2 * left_a)
        left_curv = ((1 + (2 * left_a * y_eval * self.ym_per_pix + left_b) ** 2) ** 1.5) / (denom_l if denom_l > 1e-6 else 1e-6)

        right_a = right_fit[0] * (self.xm_per_pix / (self.ym_per_pix ** 2))
        right_b = right_fit[1] * (self.xm_per_pix / self.ym_per_pix)
        denom_r = abs(2 * right_a)
        right_curv = ((1 + (2 * right_a * y_eval * self.ym_per_pix + right_b) ** 2) ** 1.5) / (denom_r if denom_r > 1e-6 else 1e-6)

        return min(3000.0, (left_curv + right_curv) / 2.0)

    def _calculate_vehicle_offset(self, left_fit: np.ndarray, right_fit: np.ndarray) -> float:
        y_eval = self.img_h
        left_x = left_fit[0] * (y_eval ** 2) + left_fit[1] * y_eval + left_fit[2]
        right_x = right_fit[0] * (y_eval ** 2) + right_fit[1] * y_eval + right_fit[2]
        lane_center = (left_x + right_x) / 2.0
        vehicle_center = self.img_w / 2.0
        # Positive = right of center, Negative = left of center
        offset_m = (vehicle_center - lane_center) * self.xm_per_pix
        return offset_m

    def _generate_lane_points(self, left_fit: np.ndarray, right_fit: np.ndarray) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        ploty = np.linspace(0, self.img_h - 1, num=30)
        left_fitx = left_fit[0] * ploty ** 2 + left_fit[1] * ploty + left_fit[2]
        right_fitx = right_fit[0] * ploty ** 2 + right_fit[1] * ploty + right_fit[2]

        pts_left_warped = np.array([np.transpose(np.vstack([left_fitx, ploty]))])
        pts_right_warped = np.array([np.flipud(np.transpose(np.vstack([right_fitx, ploty])))])

        # Unwarp back to camera perspective
        unwarped_left = cv2.perspectiveTransform(pts_left_warped, self.M_inv)[0]
        unwarped_right = cv2.perspectiveTransform(pts_right_warped, self.M_inv)[0]

        left_pts = [(int(pt[0]), int(pt[1])) for pt in unwarped_left]
        right_pts = [(int(pt[0]), int(pt[1])) for pt in unwarped_right]
        return left_pts, right_pts
