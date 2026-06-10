from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze_access_logs, analyze_gsc, estimate_index_efficiency, load_json
from .config import ensure_dirs, load_config, resolve_path
from .ftp_logs import fetch_logs
from .gsc import fetch_gsc
from .planner import generate_plan


def cmd_fetch_gsc(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    ensure_dirs(config)
    key_file = resolve_path(config, config["gsc_service_account"])
    if not key_file.exists():
        raise SystemExit(f"GSC service account not found: {key_file}")
    out = fetch_gsc(config, key_file, resolve_path(config, config["data_dir"]))
    print(out)


def cmd_fetch_logs(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    ensure_dirs(config)
    downloaded = fetch_logs(config, resolve_path(config, config["ftp"]["local_dir"]))
    for path in downloaded:
        print(path)


def cmd_analyze(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    ensure_dirs(config)
    out = run_analysis(config)
    print(out)


def cmd_weekly(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    ensure_dirs(config)
    if not args.skip_gsc:
        key_file = resolve_path(config, config["gsc_service_account"])
        if key_file.exists():
            print(fetch_gsc(config, key_file, resolve_path(config, config["data_dir"])))
        else:
            print(f"skip GSC: service account not found: {key_file}")
    if not args.skip_logs:
        try:
            for path in fetch_logs(config, resolve_path(config, config["ftp"]["local_dir"])):
                print(path)
        except RuntimeError as exc:
            print(f"skip logs: {exc}")
    print(run_analysis(config))


def run_analysis(config: dict) -> Path:
    data_dir = resolve_path(config, config["data_dir"])
    reports_dir = resolve_path(config, config["reports_dir"])
    gsc_data = load_json(data_dir / "gsc_latest.json")
    log_dir = resolve_path(config, config["ftp"]["local_dir"])
    log_paths = sorted([p for p in log_dir.glob("*") if p.is_file()])
    gsc = analyze_gsc(gsc_data, config.get("analysis", {}))
    access = analyze_access_logs(log_paths)
    efficiency = estimate_index_efficiency(
        gsc,
        int(config.get("analysis", {}).get("indexed_pages_estimate", 0)),
    )
    summary_path = data_dir / "analysis_latest.json"
    summary_path.write_text(
        json.dumps({"gsc": gsc, "access": access, "efficiency": efficiency}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return generate_plan(config, gsc, access, efficiency, reports_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kgrowth")
    parser.add_argument("--config", default="config.json")
    sub = parser.add_subparsers(required=True)

    fetch_gsc_parser = sub.add_parser("fetch-gsc")
    fetch_gsc_parser.set_defaults(func=cmd_fetch_gsc)

    fetch_logs_parser = sub.add_parser("fetch-logs")
    fetch_logs_parser.set_defaults(func=cmd_fetch_logs)

    analyze_parser = sub.add_parser("analyze")
    analyze_parser.set_defaults(func=cmd_analyze)

    weekly_parser = sub.add_parser("weekly")
    weekly_parser.add_argument("--skip-gsc", action="store_true")
    weekly_parser.add_argument("--skip-logs", action="store_true")
    weekly_parser.set_defaults(func=cmd_weekly)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
