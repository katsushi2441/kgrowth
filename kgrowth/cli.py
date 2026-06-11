from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze_access_logs, analyze_gsc, estimate_index_efficiency, load_json
from .config import domain_configs, ensure_dirs, load_config, resolve_path
from .ftp_logs import fetch_logs
from .gsc import fetch_gsc
from .improvement_jobs import write_improvement_jobs
from .planner import generate_plan


def cmd_fetch_gsc(args: argparse.Namespace) -> None:
    for config in selected_configs(args):
        ensure_dirs(config)
        key_file = resolve_path(config, config["gsc_service_account"])
        if config.get("gsc_auth", "service_account") != "gcloud" and not key_file.exists():
            raise SystemExit(f"GSC service account not found: {key_file}")
        out = fetch_gsc(config, key_file, resolve_path(config, config["data_dir"]))
        print(out)


def cmd_fetch_logs(args: argparse.Namespace) -> None:
    for config in selected_configs(args):
        ensure_dirs(config)
        downloaded = fetch_logs(config, resolve_path(config, config["ftp"]["local_dir"]))
        for path in downloaded:
            print(path)


def cmd_analyze(args: argparse.Namespace) -> None:
    for config in selected_configs(args):
        ensure_dirs(config)
        out = run_analysis(config)
        print(out)


def cmd_weekly(args: argparse.Namespace) -> None:
    for config in selected_configs(args):
        print(f"== {config.get('domain_id') or config.get('site_url')} ==")
        run_weekly_config(args, config)


def run_weekly_config(args: argparse.Namespace, config: dict) -> None:
    ensure_dirs(config)
    if not args.skip_gsc:
        key_file = resolve_path(config, config["gsc_service_account"])
        if config.get("gsc_auth", "service_account") == "gcloud" or key_file.exists():
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


def selected_configs(args: argparse.Namespace) -> list[dict]:
    config = load_config(args.config)
    return domain_configs(config, selected=args.domain)


def run_analysis(config: dict) -> Path:
    data_dir = resolve_path(config, config["data_dir"])
    reports_dir = resolve_path(config, config["reports_dir"])
    gsc_data = load_json(data_dir / "gsc_latest.json")
    log_dir = resolve_path(config, config["ftp"]["local_dir"])
    log_paths = select_log_paths(log_dir, config.get("ftp", {}))
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
    write_improvement_jobs(config, gsc, access, data_dir)
    return generate_plan(config, gsc, access, efficiency, reports_dir)


def select_log_paths(log_dir: Path, ftp_config: dict) -> list[Path]:
    paths = sorted([p for p in log_dir.glob("*") if p.is_file()])
    if ftp_config.get("parse_mode", "latest_snapshot") != "latest_snapshot":
        return paths
    stamped = [p for p in paths if len(p.name) > 16 and p.name[:15].replace("_", "").isdigit()]
    if not stamped:
        return paths
    newest = max(p.name[:15] for p in stamped)
    return [p for p in stamped if p.name.startswith(newest)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kgrowth")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--config", default="config.json")
    parent.add_argument("--domain", default=None, help="Run only one config.domains entry by id.")
    sub = parser.add_subparsers(required=True)

    fetch_gsc_parser = sub.add_parser("fetch-gsc", parents=[parent])
    fetch_gsc_parser.set_defaults(func=cmd_fetch_gsc)

    fetch_logs_parser = sub.add_parser("fetch-logs", parents=[parent])
    fetch_logs_parser.set_defaults(func=cmd_fetch_logs)

    analyze_parser = sub.add_parser("analyze", parents=[parent])
    analyze_parser.set_defaults(func=cmd_analyze)

    weekly_parser = sub.add_parser("weekly", parents=[parent])
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
