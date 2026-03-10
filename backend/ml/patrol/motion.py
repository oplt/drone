from __future__ import annotations

import cv2

from backend.ml.patrol.models import FramePacket


class MotionPrefilter:
    def __init__(self, min_motion_area: int = 1500):
        self.subtractor = cv2.createBackgroundSubtractorMOG2(
            history=200,
            varThreshold=25,
            detectShadows=False,
        )
        self.min_motion_area = int(min_motion_area)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def has_motion(self, packet: FramePacket) -> tuple[bool, dict]:
        mask = self.subtractor.apply(packet.image)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        areas = [cv2.contourArea(c) for c in contours]
        max_area = max(areas) if areas else 0.0
        return max_area >= self.min_motion_area, {
            "max_motion_area": float(max_area),
            "num_regions": len(contours),
        }
