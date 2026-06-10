from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .access_log import parse_logs, page_type


def expected_ctr(pos: float) -> float:
    if pos <= 1:
        return 0.28
    if pos <= 2:
        return 0.15
    if pos <= 3:
        return 0.10
    if pos <= 5:
        return 0.06
    if pos <= 10:
        return 0.025
    return 0.005


def tokenize(query: str) -> list[str]:
    parts = re.split(r"[\s　]+", query.strip())
    tokens: list[str] = []
    for part in parts:
        part = part.strip()
        if len(part) >= 2:
            tokens.append(part)
        if re.match(r"^[A-Za-z0-9-]{4,}$", part):
            tokens.append(part.upper())
    return tokens


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def analyze_gsc(data: dict[str, Any] | None, options: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {
            "available": False,
            "total_impressions": 0,
            "total_clicks": 0,
            "queries": 0,
            "title_fixes": [],
            "boost_queries": [],
            "hub_topics": [],
            "page_types": {},
        }

    by_query: dict[str, dict[str, Any]] = {}
    total_imp = 0
    total_clk = 0
    for row in data.get("query_page", []):
        keys = row.get("keys", [])
        if len(keys) < 2:
            continue
        query, page = keys[0], keys[1]
        imp = int(row.get("impressions", 0))
        clk = int(row.get("clicks", 0))
        pos = float(row.get("position", 999))
        total_imp += imp
        total_clk += clk
        entry = by_query.setdefault(query, {"imp": 0, "clk": 0, "pos_sum": 0.0, "pages": Counter()})
        entry["imp"] += imp
        entry["clk"] += clk
        entry["pos_sum"] += pos * imp
        entry["pages"][page] += imp

    for entry in by_query.values():
        entry["pos"] = entry["pos_sum"] / entry["imp"] if entry["imp"] else 999
        entry["ctr"] = entry["clk"] / entry["imp"] if entry["imp"] else 0
        entry["top_page"] = entry["pages"].most_common(1)[0][0] if entry["pages"] else ""

    title_min = int(options.get("title_min_impressions", 10))
    boost_min = int(options.get("boost_min_impressions", 5))
    title_fixes = []
    boost_queries = []
    for query, entry in by_query.items():
        if entry["pos"] <= 10 and entry["imp"] >= title_min and entry["ctr"] < expected_ctr(entry["pos"]) * 0.5:
            title_fixes.append(_query_row(query, entry))
        if 10 < entry["pos"] <= 30 and entry["imp"] >= boost_min:
            boost_queries.append(_query_row(query, entry))

    title_fixes.sort(key=lambda row: row["impressions"], reverse=True)
    boost_queries.sort(key=lambda row: row["impressions"], reverse=True)

    token_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"impressions": 0, "queries": 0})
    for query, entry in by_query.items():
        for token in set(tokenize(query)):
            token_stats[token]["impressions"] += int(entry["imp"])
            token_stats[token]["queries"] += 1
    hub_min = int(options.get("hub_min_queries", 3))
    hub_topics = [
        {"topic": token, **stats}
        for token, stats in token_stats.items()
        if stats["queries"] >= hub_min
    ]
    hub_topics.sort(key=lambda row: row["impressions"], reverse=True)

    page_types: dict[str, dict[str, int]] = defaultdict(lambda: {"pages": 0, "impressions": 0, "clicks": 0})
    for row in data.get("pages", []):
        keys = row.get("keys", [])
        if not keys:
            continue
        kind = page_type(keys[0])
        page_types[kind]["pages"] += 1
        page_types[kind]["impressions"] += int(row.get("impressions", 0))
        page_types[kind]["clicks"] += int(row.get("clicks", 0))

    return {
        "available": True,
        "site": data.get("site", ""),
        "start": data.get("start", ""),
        "end": data.get("end", ""),
        "total_impressions": total_imp,
        "total_clicks": total_clk,
        "ctr": total_clk / total_imp if total_imp else 0,
        "queries": len(by_query),
        "title_fixes": title_fixes,
        "boost_queries": boost_queries,
        "hub_topics": hub_topics,
        "page_types": dict(sorted(page_types.items(), key=lambda item: item[1]["impressions"], reverse=True)),
    }


def _query_row(query: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": query,
        "position": round(float(entry["pos"]), 2),
        "impressions": int(entry["imp"]),
        "clicks": int(entry["clk"]),
        "ctr": round(float(entry["ctr"]), 4),
        "page": entry["top_page"],
    }


def analyze_access_logs(log_paths: list[Path]) -> dict[str, Any]:
    return parse_logs(log_paths)


def estimate_index_efficiency(gsc: dict[str, Any], indexed_pages_estimate: int) -> dict[str, Any]:
    impressions = int(gsc.get("total_impressions", 0))
    if not indexed_pages_estimate:
        return {"indexed_pages_estimate": 0, "impressions_per_page": 0}
    return {
        "indexed_pages_estimate": indexed_pages_estimate,
        "impressions_per_page": impressions / indexed_pages_estimate,
        "impressions_per_page_rounded": round(impressions / indexed_pages_estimate, 6),
    }
