from __future__ import annotations

import os
from datetime import datetime

import cv2


class EvidenceRecorder:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        os.makedirs(self.root_dir, exist_ok=True)

    def save_frame(self, frame, prefix: str = "event") -> str:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(self.root_dir, f"{prefix}_{ts}.jpg")
        cv2.imwrite(path, frame)
        return path
