from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any


SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _json_b64url(data: dict[str, Any]) -> str:
    return _b64url(json.dumps(data, separators=(",", ":")).encode("utf-8"))


def _sign_rs256(private_key: str, signing_input: str) -> bytes:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except Exception:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=True) as key_file:
            key_file.write(private_key)
            key_file.flush()
            proc = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", key_file.name],
                input=signing_input.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip())
        return proc.stdout

    key = serialization.load_pem_private_key(private_key.encode("utf-8"), password=None)
    return key.sign(signing_input.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())


def get_access_token(service_account_json: Path) -> str:
    with service_account_json.open("r", encoding="utf-8") as f:
        key = json.load(f)
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": key["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = f"{_json_b64url(header)}.{_json_b64url(claim)}"
    jwt = f"{signing_input}.{_b64url(_sign_rs256(key['private_key'], signing_input))}"
    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        }
    ).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode("utf-8"))
    if "access_token" not in payload:
        raise RuntimeError(f"GSC token request failed: {payload}")
    return payload["access_token"]


def get_gcloud_access_token() -> str:
    proc = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gcloud auth print-access-token failed")
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return token


def query_search_analytics(token: str, site_url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    url = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        + urllib.parse.quote(site_url, safe="")
        + "/searchAnalytics/query"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"GSC API HTTP {exc.code}: {text}") from exc
    return payload.get("rows", [])


def fetch_all(
    token: str,
    site_url: str,
    dimensions: list[str],
    start: str,
    end: str,
    row_limit: int,
) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    start_row = 0
    while True:
        rows = query_search_analytics(
            token,
            site_url,
            {
                "startDate": start,
                "endDate": end,
                "dimensions": dimensions,
                "rowLimit": row_limit,
                "startRow": start_row,
            },
        )
        all_rows.extend(rows)
        if len(rows) < row_limit:
            break
        start_row += row_limit
    return all_rows


def fetch_gsc(config: dict[str, Any], key_file: Path, out_dir: Path) -> Path:
    end_date = date.today() - timedelta(days=2)
    start_date = date.today() - timedelta(days=int(config["days_back"]) + 2)
    auth_mode = config.get("gsc_auth", "service_account")
    if auth_mode == "gcloud":
        token = get_gcloud_access_token()
    else:
        token = get_access_token(key_file)
    site_url = config["site_url"]
    row_limit = int(config.get("row_limit", 25000))
    result = {
        "site": site_url,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "query_page": fetch_all(token, site_url, ["query", "page"], start_date.isoformat(), end_date.isoformat(), row_limit),
        "pages": fetch_all(token, site_url, ["page"], start_date.isoformat(), end_date.isoformat(), row_limit),
        "dates": fetch_all(token, site_url, ["date"], start_date.isoformat(), end_date.isoformat(), row_limit),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "gsc_latest.json"
    latest.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    history = out_dir / f"gsc_{date.today().strftime('%Y%m%d')}.json"
    history.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    return latest
