"""
Abstract Base Class for Modular Lane Detection Algorithms.
"""

from abc import ABC, abstractmethod
import numpy as np
from shared.protocols.message_schemas import LaneData


class LaneDetectorBase(ABC):
    @abstractmethod
    def detect(self, frame_bgr: np.ndarray) -> LaneData:
        """
        Processes a raw BGR frame and returns detected lane boundaries, curvature, and departure status.
        """
        pass
