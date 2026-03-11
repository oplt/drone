from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.ml.patrol.config import MLRuntimeSettings


class MLRuntimeSettingsTests(unittest.TestCase):
    def test_reads_ml_settings_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "ML_ENABLED=1",
                        "ML_DETECTOR_MODEL_PATH=models/custom.pt",
                        "ML_FRAME_STRIDE=4",
                    ]
                ),
                encoding="utf-8",
            )

            settings = MLRuntimeSettings(_env_file=env_path)

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.detector_model_path, "models/custom.pt")
        self.assertEqual(settings.frame_stride, 4)

    def test_uses_default_detector_model_when_env_value_is_missing(self) -> None:
        settings = MLRuntimeSettings(_env_file=None)

        self.assertEqual(settings.detector_model_path, "yolov8n.pt")


if __name__ == "__main__":
    unittest.main()
