"""Fail CI when deployable Compose files contain known development secrets."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = (ROOT / "docker-compose.yml",)
FORBIDDEN = (
    "postgresql+asyncpg://drone:drone@",
    "POSTGRES_PASSWORD: drone",
    "MINIO_ROOT_PASSWORD: minioadmin",
    "JWT_SECRET: local-dev-secret-CHANGE-ME",
    "dev-placeholder",
)
INLINE_PASSWORD = re.compile(r"://[^\s:@]+:(?:drone|change-me|password|minioadmin)@", re.I)


def main() -> int:
    findings: list[str] = []
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN:
            if needle in text:
                findings.append(f"{path.relative_to(ROOT)}: {needle}")
        if INLINE_PASSWORD.search(text):
            findings.append(f"{path.relative_to(ROOT)}: inline development password")
    if findings:
        print("Secret scan failed:")
        print("\n".join(f"- {finding}" for finding in findings))
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
