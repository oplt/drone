from __future__ import annotations


def extract_lonlat_pairs(node: object) -> list[tuple[float, float]]:
    """Flatten nested coordinate containers into numeric lon/lat pairs."""
    if not isinstance(node, (list, tuple)):
        return []
    if len(node) >= 2 and isinstance(node[0], (int, float)) and isinstance(node[1], (int, float)):
        return [(float(node[0]), float(node[1]))]
    pairs: list[tuple[float, float]] = []
    for child in node:
        pairs.extend(extract_lonlat_pairs(child))
    return pairs
