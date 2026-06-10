from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "site_url": "https://aixec.exbridge.jp/",
    "days_back": 28,
    "gsc_service_account": "secrets/gsc-service-account.json",
    "data_dir": "data",
    "reports_dir": "reports",
    "row_limit": 25000,
    "ftp": {
        "host_env": "KGROWTH_FTP_HOST",
        "user_env": "KGROWTH_FTP_USER",
        "pass_env": "KGROWTH_FTP_PASS",
        "remote_paths": [],
        "local_dir": "data/access_logs",
    },
    "analysis": {
        "indexed_pages_estimate": 0,
        "title_min_impressions": 10,
        "boost_min_impressions": 5,
        "hub_min_queries": 3,
        "max_rows": 40,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    config = DEFAULT_CONFIG
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            config = deep_merge(DEFAULT_CONFIG, json.load(f))
    root = config_path.resolve().parent if config_path.exists() else Path.cwd()
    config["_root"] = str(root)
    return config


def resolve_path(config: dict[str, Any], value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(config["_root"]) / path


def ensure_dirs(config: dict[str, Any]) -> None:
    resolve_path(config, config["data_dir"]).mkdir(parents=True, exist_ok=True)
    resolve_path(config, config["reports_dir"]).mkdir(parents=True, exist_ok=True)
    ftp_local = config.get("ftp", {}).get("local_dir")
    if ftp_local:
        resolve_path(config, ftp_local).mkdir(parents=True, exist_ok=True)
