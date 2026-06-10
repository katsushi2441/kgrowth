from __future__ import annotations

import ftplib
import os
import re
from datetime import datetime
from pathlib import Path


def _read_legacy_helper(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    helper = Path(path).expanduser()
    if not helper.is_file():
        return {}
    text = helper.read_text(encoding="utf-8", errors="ignore")
    values: dict[str, str] = {}
    for key in ("FTP_HOST", "FTP_USER", "FTP_PASS"):
        match = re.search(rf"^{key}\s*=\s*(['\"])(.*?)\1", text, re.MULTILINE)
        if match:
            values[key] = match.group(2)
    return values


def _setting(ftp_config: dict, key: str, env_key: str, legacy: dict[str, str], legacy_key: str) -> str:
    value = os.environ.get(env_key) or ftp_config.get(key) or legacy.get(legacy_key)
    if not value:
        raise RuntimeError(f"missing FTP setting: {key} or environment variable {env_key}")
    return value


def _safe_name(remote_path: str) -> str:
    return remote_path.strip("/").replace("/", "__") or "root"


def fetch_logs(config: dict, out_dir: Path) -> list[Path]:
    ftp_config = config.get("ftp", {})
    legacy = _read_legacy_helper(ftp_config.get("legacy_helper"))
    host = _setting(ftp_config, "host", ftp_config.get("host_env", "KGROWTH_FTP_HOST"), legacy, "FTP_HOST")
    user = _setting(ftp_config, "user", ftp_config.get("user_env", "KGROWTH_FTP_USER"), legacy, "FTP_USER")
    password = _setting(ftp_config, "password", ftp_config.get("pass_env", "KGROWTH_FTP_PASS"), legacy, "FTP_PASS")
    remote_paths = ftp_config.get("remote_paths", [])
    if not remote_paths:
        raise RuntimeError("ftp.remote_paths is empty")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    with ftplib.FTP(host, timeout=45) as ftp:
        ftp.login(user, password)
        for remote in remote_paths:
            downloaded.extend(_download_path(ftp, remote, out_dir, stamp))
    return downloaded


def _download_path(ftp: ftplib.FTP, remote: str, out_dir: Path, stamp: str) -> list[Path]:
    current = ftp.pwd()
    try:
        ftp.cwd(remote)
        names = ftp.nlst()
        files: list[Path] = []
        for name in names:
            lower = name.lower()
            if "access" not in lower and "log" not in lower:
                continue
            files.extend(_download_path(ftp, f"{remote.rstrip('/')}/{name}", out_dir, stamp))
        return files
    except ftplib.error_perm:
        ftp.cwd(current)

    local = out_dir / f"{stamp}_{_safe_name(remote)}"
    with local.open("wb") as f:
        ftp.retrbinary(f"RETR {remote}", f.write)
    return [local]
