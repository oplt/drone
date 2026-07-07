from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_ENV = ROOT / "backend" / "test.env.example"


def _load_env(path: Path) -> dict[str, str]:
    env = os.environ.copy()
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def _run(args: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def _wait_for_db(env: dict[str, str], *, timeout_s: float) -> None:
    script = """
import asyncio
import os
import asyncpg

async def main():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    await conn.execute("select 1")
    await conn.close()

asyncio.run(main())
"""
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        last_error = (result.stderr or result.stdout).strip()
        time.sleep(1.0)
    raise RuntimeError(f"PostgreSQL did not become ready within {timeout_s:.0f}s: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backend tests with local test env defaults.")
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run tests marked integration instead of the non-integration suite.",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Do not run Alembic migrations before pytest.",
    )
    parser.add_argument(
        "--wait-db",
        action="store_true",
        help="Wait for DATABASE_URL to accept connections before running migrations/tests.",
    )
    parser.add_argument("pytest_args", nargs="*", help="Extra pytest arguments.")
    args = parser.parse_args()

    env = _load_env(TEST_ENV)
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    if args.wait_db:
        _wait_for_db(env, timeout_s=90.0)

    if not args.skip_migrations:
        _run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "backend/alembic.ini",
                "upgrade",
                "head",
            ],
            env=env,
        )

    marker = "integration" if args.integration else "not integration"
    pytest_cmd = [sys.executable, "-m", "pytest", "backend/tests", "-m", marker, *args.pytest_args]
    _run(pytest_cmd, env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
