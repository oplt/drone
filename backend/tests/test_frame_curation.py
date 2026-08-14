from types import SimpleNamespace

from backend.modules.vision_models.service.dataset_service import (
    apply_dataset_near_duplicate_clustering,
)
from backend.modules.vision_models.service.frame_curation import (
    hash_distance,
    prefix_probe_keys,
)


def test_prefix_probes_detect_near_duplicate_across_different_prefixes():
    first_hash = "0000000000000000"
    second_hash = "0010000000000000"
    assert first_hash[:3] != second_hash[:3]
    assert hash_distance(first_hash, second_hash) <= 6
    assert second_hash[:3] in prefix_probe_keys(first_hash)

    images = [
        SimpleNamespace(
            id="image-a",
            selected=True,
            perceptual_hash=first_hash,
            metadata_json={},
        ),
        SimpleNamespace(
            id="image-b",
            selected=True,
            perceptual_hash=second_hash,
            metadata_json={},
        ),
    ]
    summary = apply_dataset_near_duplicate_clustering(images)

    assert summary["near_duplicate_rejected"] == 1
    assert images[1].selected is False
