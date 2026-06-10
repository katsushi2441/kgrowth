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

BOT_WORDS = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "crawl",
    "mediapartners",
    "curl",
    "wget",
    "python",
    "httpclient",
    "scrapy",
    "headless",
    "phantom",
    "selenium",
    "playwright",
    "puppeteer",
    "facebookexternalhit",
    "meta-externalagent",
    "twitterbot",
    "slackbot",
    "discordbot",
    "linebot",
    "googlebot",
    "googleother",
    "google-read-aloud",
    "bingbot",
    "duckduckbot",
    "baiduspider",
    "yandexbot",
    "ahrefsbot",
    "semrushbot",
    "mj12bot",
    "petalbot",
    "bytespider",
    "claudebot",
    "gptbot",
    "oai-searchbot",
    "ccbot",
    "perplexitybot",
    "applebot",
    "amazonbot",
)
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


def is_bot_ua(ua: str) -> bool:
    ua = ua.lower().strip()
    if not ua:
        return True
    return any(word in ua for word in BOT_WORDS)


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def parse_logs(paths: Iterable[Path]) -> dict:
    total = 0
    raw_total = 0
    unique_ips: set[str] = set()
    raw_unique_ips: set[str] = set()
    status = Counter()
    pages = Counter()
    referers = Counter()
    user_agents = Counter()
    types = Counter()
    bots = 0
    not_found = Counter()
    search_terms = Counter()
    go_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"clicks": 0, "raw_clicks": 0})
    go_products: dict[str, dict[str, str | int]] = {}
    go_sources: dict[str, dict[str, str | int]] = {}
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
                raw_total += 1
                ip = row["ip"].strip()
                raw_unique_ips.add(ip)
                ua = row.get("ua", "")
                if is_bot_ua(ua):
                    bots += 1
                    continue

                total += 1
                unique_ips.add(ip)
                parsed = urllib.parse.urlparse(request_path)
                page_key = parsed.path or "/"
                pages[page_key] += 1
                types[page_type(request_path)] += 1
                if row.get("status") == "404":
                    not_found[page_key] += 1
                referer = row.get("referer", "").strip()
                if page_key.endswith("/go.php") or page_key == "/go.php":
                    _track_go_click(parsed, referer, go_totals, go_products, go_sources, row.get("time", ""))
                if referer and referer != "-":
                    referers[urllib.parse.urlparse(referer).netloc or referer] += 1
                user_agents[ua[:140]] += 1
                query = urllib.parse.parse_qs(parsed.query)
                for key in SEARCH_PARAMS:
                    for value in query.get(key, []):
                        if value.strip():
                            search_terms[value.strip()] += 1

    return {
        "files": files,
        "total_requests": total,
        "raw_requests": raw_total,
        "unique_ips": len(unique_ips),
        "raw_unique_ips": len(raw_unique_ips),
        "bot_requests": bots,
        "bot_ratio": (bots / raw_total) if raw_total else 0,
        "status": dict(status.most_common()),
        "page_types": dict(types.most_common()),
        "top_pages": dict(pages.most_common(50)),
        "top_referers": dict(referers.most_common(30)),
        "top_404": dict(not_found.most_common(30)),
        "search_terms": dict(search_terms.most_common(50)),
        "top_user_agents": dict(user_agents.most_common(20)),
        "affiliate_clicks": dict(go_totals),
        "top_affiliate_products": sorted(
            go_products.values(),
            key=lambda row: (int(row.get("clicks", 0)), int(row.get("raw_clicks", 0)), str(row.get("latest_at", ""))),
            reverse=True,
        )[:50],
        "top_affiliate_sources": sorted(
            go_sources.values(),
            key=lambda row: (int(row.get("clicks", 0)), int(row.get("raw_clicks", 0)), str(row.get("latest_at", ""))),
            reverse=True,
        )[:50],
    }


def _track_go_click(
    parsed: urllib.parse.ParseResult,
    referer: str,
    totals: dict[str, dict[str, int]],
    products: dict[str, dict[str, str | int]],
    sources: dict[str, dict[str, str | int]],
    at: str,
) -> None:
    params = urllib.parse.parse_qs(parsed.query)

    def first(name: str) -> str:
        values = params.get(name, [])
        return values[0].strip() if values else ""

    to = (first("to") or first("click") or "(unknown)").lower()
    keyword = first("kw")
    pid = first("product_id") or first("pid")
    jan = re.sub(r"\D", "", first("jan"))
    asin = first("asin").upper()
    model = first("model_number") or first("model")
    source = first("from")
    quality = first("click_quality").lower()
    likely_human = quality == "likely_human"
    if not quality:
        likely_human = bool(referer)
    if not source and referer:
        ref = urllib.parse.urlparse(referer)
        source = ref.path + (("?" + ref.query) if ref.query else "")
    if not source and not referer:
        return
    if not source:
        source = "(unknown)"
    product_label = keyword or (f"product_id:{pid}" if pid else "") or (f"JAN:{jan}" if jan else "") or (f"ASIN:{asin}" if asin else "") or model or "(unknown)"

    totals[to]["raw_clicks"] += 1
    if likely_human:
        totals[to]["clicks"] += 1

    source_key = f"{to}|{source}"
    source_row = sources.setdefault(
        source_key,
        {"to": to, "from": source, "clicks": 0, "raw_clicks": 0, "latest_at": ""},
    )
    source_row["raw_clicks"] = int(source_row["raw_clicks"]) + 1
    if likely_human:
        source_row["clicks"] = int(source_row["clicks"]) + 1
    if not source_row["latest_at"] or at > str(source_row["latest_at"]):
        source_row["latest_at"] = at

    product_key = f"{to}|{pid}|{jan}|{asin}|{model}|{source}|{product_label}"
    product_row = products.setdefault(
        product_key,
        {
            "to": to,
            "product": product_label,
            "pid": pid,
            "jan": jan,
            "asin": asin,
            "model": model,
            "from": source,
            "clicks": 0,
            "raw_clicks": 0,
            "latest_at": "",
        },
    )
    product_row["raw_clicks"] = int(product_row["raw_clicks"]) + 1
    if likely_human:
        product_row["clicks"] = int(product_row["clicks"]) + 1
    if not product_row["latest_at"] or at > str(product_row["latest_at"]):
        product_row["latest_at"] = at
