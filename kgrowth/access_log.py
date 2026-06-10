from __future__ import annotations

import gzip
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


LOG_RE = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<path>[^"]*?) (?P<proto>[^"]*)" '
    r'(?P<status>\d{3}) (?P<bytes>\S+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"'
)

BOT_WORDS = ("bot", "spider", "crawl", "slurp", "bingpreview", "facebookexternalhit", "monitor")
SEARCH_PARAMS = ("q", "query", "keyword", "s", "p")


def page_type(path: str) -> str:
    parsed = urllib.parse.urlparse(path)
    clean = parsed.path
    if clean in ("", "/"):
        return "top"
    if "product" in clean or "market" in clean:
        return "product"
    if "sns.php" in clean:
        return "sns"
    if "aixtube" in clean or "/video/" in clean:
        return "aixtube"
    if "ranking" in clean:
        return "ranking"
    if "go.php" in clean:
        return "affiliate"
    return "other"


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def parse_logs(paths: Iterable[Path]) -> dict:
    total = 0
    unique_ips: set[str] = set()
    status = Counter()
    pages = Counter()
    referers = Counter()
    user_agents = Counter()
    types = Counter()
    bots = 0
    not_found = Counter()
    search_terms = Counter()
    files: list[str] = []

    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        files.append(str(path))
        with _open_text(path) as f:
            for line in f:
                row = None
                request_path = ""
                if "|" in line and line[:4].isdigit():
                    parts = [part.strip() for part in line.rstrip("\n").split("|", 4)]
                    if len(parts) != 5:
                        continue
                    row = {
                        "time": parts[0],
                        "ip": parts[1],
                        "url": parts[2],
                        "referer": parts[3],
                        "ua": parts[4],
                    }
                    request_path = row["url"]
                    if not request_path:
                        continue
                    parsed_url = urllib.parse.urlparse(request_path)
                    if parsed_url.scheme and parsed_url.netloc:
                        request_path = urllib.parse.urlunparse(("", "", parsed_url.path, "", parsed_url.query, ""))
                else:
                    match = LOG_RE.search(line)
                    if not match:
                        continue
                    row = match.groupdict()
                    request_path = row["path"]
                    status[row["status"]] += 1
                if not row:
                    continue
                total += 1
                unique_ips.add(row["ip"].strip())
                parsed = urllib.parse.urlparse(request_path)
                page_key = parsed.path or "/"
                pages[page_key] += 1
                types[page_type(request_path)] += 1
                if row.get("status") == "404":
                    not_found[page_key] += 1
                referer = row.get("referer", "").strip()
                if referer and referer != "-":
                    referers[urllib.parse.urlparse(referer).netloc or referer] += 1
                ua = row["ua"]
                user_agents[ua[:140]] += 1
                if any(word in ua.lower() for word in BOT_WORDS):
                    bots += 1
                query = urllib.parse.parse_qs(parsed.query)
                for key in SEARCH_PARAMS:
                    for value in query.get(key, []):
                        if value.strip():
                            search_terms[value.strip()] += 1

    return {
        "files": files,
        "total_requests": total,
        "unique_ips": len(unique_ips),
        "bot_requests": bots,
        "bot_ratio": (bots / total) if total else 0,
        "status": dict(status.most_common()),
        "page_types": dict(types.most_common()),
        "top_pages": dict(pages.most_common(50)),
        "top_referers": dict(referers.most_common(30)),
        "top_404": dict(not_found.most_common(30)),
        "search_terms": dict(search_terms.most_common(50)),
        "top_user_agents": dict(user_agents.most_common(20)),
    }
