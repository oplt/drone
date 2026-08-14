#!/usr/bin/env python3
"""TASK 3.1 repeatable video decoder benchmark harness.

Compares OpenCV sequential decode, OpenCV seek, PyAV sequential sampling, and an
ffmpeg pipe/filter path without touching production decode code.

Timing methodology (documented in docs/benchmarks/video-decoder-benchmark.md):
- wall_time_seconds: ``time.monotonic()`` around the full decode/sample loop
- cpu_time_seconds: ``time.process_time()`` delta for the benchmark process
- ram_peak_mb: peak RSS sampled via psutil before/after (live mode)
- timestamp_error_max_seconds: max |expected - actual| timestamp per selected frame
- source_video_minutes_per_wall_minute: processed video minutes / wall minutes
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARKS_DIR = Path(__file__).resolve().parent
for path in (str(REPO_ROOT), str(BENCHMARKS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from video_decoder_modes import (  # noqa: E402
    ALL_MODES,
    MODE_FFMPEG_PIPE,
    MODE_PYAV_SEQUENTIAL,
    benchmark_decoder_mode,
    read_video_metadata,
    source_video_minutes_per_wall_minute,
    write_synthetic_video,
)

SUPPORTED_MANIFEST_VERSION = 1
DEFAULT_MANIFEST = Path(__file__).with_name("video_decoder_manifest.example.json")
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "benchmarks" / "video-decoder-report.json"
DEFAULT_MARKDOWN = REPO_ROOT / "docs" / "benchmarks" / "video-decoder-benchmark.md"


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("version", -1)) != SUPPORTED_MANIFEST_VERSION:
        raise SystemExit(f"Unsupported manifest version: {payload.get('version')!r}")
    for key in ("name", "modes", "sample_rates_fps", "clips"):
        if key not in payload:
            raise SystemExit(f"Manifest missing required key: {key}")
    return payload


def _sample_ram_mb() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    return float(psutil.Process().memory_info().rss) / (1024 * 1024)


def _resolve_clip_path(
    clip: dict[str, Any],
    *,
    synthesize_missing: bool,
    scratch_dir: Path,
) -> Path | None:
    raw_path = clip.get("path")
    if raw_path:
        path = Path(str(raw_path))
        if path.is_file():
            return path
    if not synthesize_missing:
        return None
    clip_id = str(clip["id"])
    output = scratch_dir / f"{clip_id}.mp4"
    if output.is_file():
        return output
    write_synthetic_video(
        output,
        fps=float(clip.get("fps", 30.0)),
        frame_count=int(clip.get("frame_count", 300)),
        width=int(clip.get("width", 1920)),
        height=int(clip.get("height", 1080)),
    )
    return output


def _row_from_result(
    *,
    clip: dict[str, Any],
    sample_rate_fps: float,
    mode: str,
    duration_seconds: float,
    result: dict[str, Any],
) -> dict[str, Any]:
    wall = float(result.get("wall_time_seconds", 0.0))
    return {
        "clip_id": clip["id"],
        "clip_label": clip.get("label", clip["id"]),
        "codec": clip.get("codec"),
        "resolution": clip.get("resolution"),
        "duration_seconds": duration_seconds,
        "sample_rate_fps": sample_rate_fps,
        "mode": mode,
        "wall_time_seconds": round(wall, 4),
        "cpu_time_seconds": round(float(result.get("cpu_time_seconds", 0.0)), 4),
        "decoded_frames": int(result.get("decoded_frames", 0)),
        "selected_frames": int(result.get("selected_frames", 0)),
        "ram_peak_mb": result.get("ram_peak_mb"),
        "timestamp_error_max_seconds": round(
            float(result.get("timestamp_error_max_seconds", 0.0)), 6
        ),
        "source_video_minutes_per_wall_minute": (
            round(
                float(result["source_video_minutes_per_wall_minute"]),
                3,
            )
            if result.get("source_video_minutes_per_wall_minute") is not None
            else None
        ),
        "available": bool(result.get("available", True)),
        "error": result.get("error"),
    }


def build_fixture_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    fixture = dict(manifest.get("fixture") or {})
    rows: list[dict[str, Any]] = []
    for clip in manifest["clips"]:
        clip_fixture = dict(fixture.get(clip["id"]) or {})
        duration = float(clip.get("duration_seconds", 0.0))
        for sample_rate in manifest["sample_rates_fps"]:
            sample_key = str(sample_rate)
            sample_fixture = dict(clip_fixture.get(sample_key) or clip_fixture.get(str(float(sample_rate))) or {})
            for mode in manifest["modes"]:
                result = dict(sample_fixture.get(mode) or {})
                if not result:
                    raise SystemExit(
                        f"Fixture missing clip={clip['id']} sample_rate={sample_rate} mode={mode}"
                    )
                rows.append(
                    _row_from_result(
                        clip=clip,
                        sample_rate_fps=float(sample_rate),
                        mode=str(mode),
                        duration_seconds=duration,
                        result=result,
                    )
                )
    return rows


def run_live_rows(
    manifest: dict[str, Any],
    *,
    synthesize_missing: bool,
    scratch_dir: Path,
    modes: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected_modes = modes or list(manifest["modes"])
    rows: list[dict[str, Any]] = []
    for clip in manifest["clips"]:
        clip_path = _resolve_clip_path(
            clip,
            synthesize_missing=synthesize_missing,
            scratch_dir=scratch_dir,
        )
        if clip_path is None:
            raise SystemExit(
                f"Clip path missing for {clip['id']}; provide path or use --synthesize-missing"
            )
        metadata = read_video_metadata(clip_path)
        duration_seconds = metadata.duration_seconds or float(
            clip.get("duration_seconds", 0.0)
        )
        for sample_rate in manifest["sample_rates_fps"]:
            for mode in selected_modes:
                if mode == MODE_PYAV_SEQUENTIAL:
                    try:
                        import av  # noqa: F401
                    except ImportError:
                        rows.append(
                            _row_from_result(
                                clip=clip,
                                sample_rate_fps=float(sample_rate),
                                mode=mode,
                                duration_seconds=duration_seconds,
                                result={
                                    "available": False,
                                    "error": "PyAV not installed",
                                    "wall_time_seconds": 0.0,
                                    "cpu_time_seconds": 0.0,
                                    "decoded_frames": 0,
                                    "selected_frames": 0,
                                    "timestamp_error_max_seconds": 0.0,
                                    "ram_peak_mb": None,
                                    "source_video_minutes_per_wall_minute": None,
                                },
                            )
                        )
                        continue
                if mode == MODE_FFMPEG_PIPE:
                    if shutil.which("ffmpeg") is None:
                        rows.append(
                            _row_from_result(
                                clip=clip,
                                sample_rate_fps=float(sample_rate),
                                mode=mode,
                                duration_seconds=duration_seconds,
                                result={
                                    "available": False,
                                    "error": "ffmpeg not found on PATH",
                                    "wall_time_seconds": 0.0,
                                    "cpu_time_seconds": 0.0,
                                    "decoded_frames": 0,
                                    "selected_frames": 0,
                                    "timestamp_error_max_seconds": 0.0,
                                    "ram_peak_mb": None,
                                    "source_video_minutes_per_wall_minute": None,
                                },
                            )
                        )
                        continue
                result = benchmark_decoder_mode(
                    mode,
                    clip_path,
                    sample_rate_fps=float(sample_rate),
                    sample_ram=_sample_ram_mb,
                )
                payload = {
                    "wall_time_seconds": result.wall_time_seconds,
                    "cpu_time_seconds": result.cpu_time_seconds,
                    "decoded_frames": result.decoded_frames,
                    "selected_frames": result.selected_frames,
                    "ram_peak_mb": result.ram_peak_mb,
                    "timestamp_error_max_seconds": result.timestamp_error_max_seconds,
                    "source_video_minutes_per_wall_minute": source_video_minutes_per_wall_minute(
                        duration_seconds=duration_seconds,
                        wall_time_seconds=result.wall_time_seconds,
                    ),
                    "available": result.available,
                    "error": result.error,
                }
                rows.append(
                    _row_from_result(
                        clip=clip,
                        sample_rate_fps=float(sample_rate),
                        mode=mode,
                        duration_seconds=duration_seconds,
                        result=payload,
                    )
                )
    return rows


def build_report(
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "version": 1,
        "mode": mode,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": {
            "name": manifest["name"],
            "modes": manifest["modes"],
            "sample_rates_fps": manifest["sample_rates_fps"],
            "clips": [
                {
                    "id": clip["id"],
                    "label": clip.get("label"),
                    "codec": clip.get("codec"),
                    "resolution": clip.get("resolution"),
                    "duration_seconds": clip.get("duration_seconds"),
                }
                for clip in manifest["clips"]
            ],
            "hardware": manifest.get("hardware"),
        },
        "timing_methodology": {
            "wall_time_seconds": "time.monotonic() around full decode/sample loop",
            "cpu_time_seconds": "time.process_time() delta for benchmark process",
            "ram_peak_mb": "psutil RSS peak sampled before/after decode",
            "timestamp_error_max_seconds": "max |expected-index/fps - actual| for selected frames",
            "source_video_minutes_per_wall_minute": "video_duration_minutes / wall_minutes",
        },
        "rows": rows,
        "adoption": analyze_decoder_adoption(rows, manifest),
        "gates": {
            "production_default_decoder": "opencv_sequential",
            "opt_in_env": "VIDEO_ANALYSIS_DECODER",
            "change_default_only_after_live_benchmark": True,
        },
    }


def analyze_decoder_adoption(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    baseline_mode = str(manifest.get("baseline_mode", "opencv_sequential"))
    cpu_threshold = float(manifest.get("adoption_cpu_threshold_percent", 30.0))
    wall_threshold = float(manifest.get("adoption_wall_threshold_percent", 25.0))
    ts_threshold = float(manifest.get("adoption_timestamp_error_max_seconds", 0.1))
    grouped: dict[tuple[str, float], dict[str, dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["clip_id"]), float(row["sample_rate_fps"]))
        grouped.setdefault(key, {})[str(row["mode"])] = row

    comparisons: list[dict[str, Any]] = []
    for (clip_id, sample_rate), modes in sorted(grouped.items()):
        baseline = modes.get(baseline_mode)
        if baseline is None:
            continue
        base_cpu = float(baseline.get("cpu_time_seconds") or 0.0)
        base_wall = float(baseline.get("wall_time_seconds") or 0.0)
        for mode, row in sorted(modes.items()):
            if mode == baseline_mode:
                continue
            if not row.get("available", True):
                comparisons.append(
                    {
                        "clip_id": clip_id,
                        "sample_rate_fps": sample_rate,
                        "mode": mode,
                        "meets_threshold": False,
                        "available": False,
                        "error": row.get("error"),
                    }
                )
                continue
            cpu_improve = (
                ((base_cpu - float(row["cpu_time_seconds"])) / base_cpu) * 100.0
                if base_cpu > 0
                else 0.0
            )
            wall_improve = (
                ((base_wall - float(row["wall_time_seconds"])) / base_wall) * 100.0
                if base_wall > 0
                else 0.0
            )
            ts_ok = float(row.get("timestamp_error_max_seconds") or 0.0) <= ts_threshold
            meets = ts_ok and (
                cpu_improve >= cpu_threshold or wall_improve >= wall_threshold
            )
            comparisons.append(
                {
                    "clip_id": clip_id,
                    "sample_rate_fps": sample_rate,
                    "mode": mode,
                    "cpu_improvement_percent": round(cpu_improve, 2),
                    "wall_improvement_percent": round(wall_improve, 2),
                    "timestamp_error_max_seconds": row.get(
                        "timestamp_error_max_seconds"
                    ),
                    "meets_threshold": meets,
                    "available": True,
                }
            )

    qualifying = [row for row in comparisons if row.get("meets_threshold")]
    recommended = None
    if qualifying:
        recommended = sorted(
            qualifying,
            key=lambda row: (
                -float(row.get("wall_improvement_percent") or 0.0),
                -float(row.get("cpu_improvement_percent") or 0.0),
            ),
        )[0]["mode"]
    return {
        "baseline_mode": baseline_mode,
        "cpu_threshold_percent": cpu_threshold,
        "wall_threshold_percent": wall_threshold,
        "timestamp_error_max_seconds": ts_threshold,
        "qualifying_cases": len(qualifying),
        "recommend_default_change": False,
        "recommended_opt_in_decoder": recommended,
        "reason": (
            "Fixture/live report shows threshold wins, but production default stays "
            "opencv_sequential until representative hardware validation is recorded."
            if qualifying
            else "No alternative decoder met adoption thresholds with acceptable timestamps."
        ),
        "comparisons": comparisons,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "clip_id",
        "clip_label",
        "codec",
        "resolution",
        "duration_seconds",
        "sample_rate_fps",
        "mode",
        "wall_time_seconds",
        "cpu_time_seconds",
        "decoded_frames",
        "selected_frames",
        "ram_peak_mb",
        "timestamp_error_max_seconds",
        "source_video_minutes_per_wall_minute",
        "available",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Video decoder benchmark",
        "",
        "Repeatable harness for TASK 3.1. Compares decoder strategies without",
        "changing production code in ``backend/shared/media_frames.py``.",
        "",
        "## Runbook",
        "",
        "Fixture (machine-readable placeholders):",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \\",
        "  --fixture --output docs/benchmarks/video-decoder-report.json",
        "python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \\",
        "  --render-markdown docs/benchmarks/video-decoder-report.json \\",
        "  --markdown-output docs/benchmarks/video-decoder-benchmark.md",
        "```",
        "",
        "Live OpenCV modes with synthetic clips when paths are absent:",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \\",
        "  --synthesize-missing --modes opencv_sequential,opencv_seek \\",
        "  --output /tmp/video-decoder-live.json",
        "```",
        "",
        "Live against real 1080p/4K assets (set ``path`` in manifest clips):",
        "",
        "```sh",
        "python3 backend/scripts/benchmarks/run_video_decoder_benchmark.py \\",
        "  --manifest backend/scripts/benchmarks/video_decoder_manifest.example.json \\",
        "  --output /tmp/video-decoder-live.json \\",
        "  --csv-output /tmp/video-decoder-live.csv",
        "```",
        "",
        "## Timing methodology",
        "",
        "| Metric | Definition |",
        "|--------|------------|",
        "| wall_time_seconds | ``time.monotonic()`` around full decode/sample loop |",
        "| cpu_time_seconds | ``time.process_time()`` delta for benchmark process |",
        "| ram_peak_mb | psutil RSS peak sampled before/after decode |",
        "| timestamp_error_max_seconds | max \\|expected − actual\\| timestamp on selected frames |",
        "| source_video_minutes_per_wall_minute | processed video minutes / wall-clock minutes |",
        "",
        "Modes:",
        "",
        "- **opencv_sequential** — decode every frame sequentially; keep sampled indices",
        "- **opencv_seek** — ``CAP_PROP_POS_FRAMES`` seek to sampled indices",
        "- **pyav_sequential** — PyAV sequential decode with stride sampling",
        "- **ffmpeg_pipe** — ``ffmpeg`` ``fps`` filter to rawvideo pipe",
        "",
        f"- Report mode: `{report['mode']}`",
        f"- Manifest: `{report['manifest']['name']}`",
        "",
        "## Results",
        "",
        "| clip | sample FPS | mode | wall s | CPU s | decoded | selected | RAM MiB | ts err s | vid min / wall min |",
        "|------|----------:|------|-------:|------:|--------:|---------:|--------:|---------:|-------------------:|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {clip} | {sample} | {mode} | {wall:.2f} | {cpu:.2f} | {decoded} | {selected} | {ram} | {ts:.4f} | {throughput} |".format(
                clip=row["clip_id"],
                sample=row["sample_rate_fps"],
                mode=row["mode"],
                wall=float(row["wall_time_seconds"]),
                cpu=float(row["cpu_time_seconds"]),
                decoded=row["decoded_frames"],
                selected=row["selected_frames"],
                ram=(
                    f"{float(row['ram_peak_mb']):.0f}"
                    if row.get("ram_peak_mb") is not None
                    else "n/a"
                ),
                ts=float(row["timestamp_error_max_seconds"]),
                throughput=(
                    f"{float(row['source_video_minutes_per_wall_minute']):.2f}"
                    if row.get("source_video_minutes_per_wall_minute") is not None
                    else "n/a"
                ),
            )
        )
    if report["mode"] == "fixture":
        lines.extend(
            [
                "",
                "> Fixture timings are synthetic placeholders. Replace by running live",
                "> commands against representative 1080p/4K H.264/H.265 clips.",
                "",
            ]
        )
    unavailable = [row for row in report["rows"] if not row.get("available", True)]
    if unavailable:
        lines.extend(["## Skipped modes", ""])
        for row in unavailable:
            lines.append(
                f"- `{row['clip_id']}` @ {row['sample_rate_fps']} FPS `{row['mode']}`: "
                f"{row.get('error') or 'unavailable'}"
            )
        lines.append("")
    adoption = report.get("adoption")
    if adoption:
        lines.extend(
            [
                "## Adoption analysis (TASK 3.2)",
                "",
                f"- Baseline mode: `{adoption['baseline_mode']}`",
                f"- CPU threshold: `{adoption['cpu_threshold_percent']}%`",
                f"- Wall-time threshold: `{adoption['wall_threshold_percent']}%`",
                f"- Qualifying cases: `{adoption['qualifying_cases']}`",
                f"- Recommend default change: **{'yes' if adoption['recommend_default_change'] else 'no'}**",
                f"- Suggested opt-in decoder: `{adoption.get('recommended_opt_in_decoder') or 'none'}`",
                f"- Notes: {adoption['reason']}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Benchmark manifest JSON",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use synthetic timings from manifest fixture (no decode).",
    )
    parser.add_argument(
        "--synthesize-missing",
        action="store_true",
        help="Generate synthetic mp4 clips when manifest paths are absent (live mode).",
    )
    parser.add_argument(
        "--modes",
        help="Comma-separated subset of modes for live runs.",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=Path("/tmp/drone_app_video_decoder_benchmark"),
        help="Directory for synthesized clips.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON report output path",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        help="Optional CSV flatten output path",
    )
    parser.add_argument(
        "--render-markdown",
        type=Path,
        help="Render markdown from an existing JSON report path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN,
        help="Markdown output path when rendering a report.",
    )
    args = parser.parse_args()

    if args.render_markdown:
        report = json.loads(args.render_markdown.read_text(encoding="utf-8"))
        markdown = render_markdown(report)
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")
        print(json.dumps({"markdown_output": str(args.markdown_output)}, indent=2))
        return 0

    manifest = load_manifest(args.manifest)
    if args.fixture:
        rows = build_fixture_rows(manifest)
        report_mode = "fixture"
    else:
        selected_modes = (
            [item.strip() for item in args.modes.split(",") if item.strip()]
            if args.modes
            else None
        )
        if selected_modes:
            unknown = sorted(set(selected_modes) - set(ALL_MODES))
            if unknown:
                raise SystemExit(f"Unknown modes: {', '.join(unknown)}")
        rows = run_live_rows(
            manifest,
            synthesize_missing=args.synthesize_missing,
            scratch_dir=args.scratch_dir,
            modes=selected_modes,
        )
        report_mode = "live"
    report = build_report(manifest, rows, mode=report_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.csv_output:
        write_csv(rows, args.csv_output)
    print(json.dumps({"output": str(args.output), "mode": report_mode, "rows": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
