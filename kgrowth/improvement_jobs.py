from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _job_id(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _base_job(kind: str, title: str, priority: int, app: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _job_id(kind, payload),
        "kind": kind,
        "title": title,
        "priority": priority,
        "status": "proposed",
        "project": "kgrowth",
        "target_app": app,
        "action": action,
        "payload": payload,
        "success_rule": "",
        "cooldown_minutes": 60,
        "max_attempts_per_day": 3,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def generate_improvement_jobs(config: dict[str, Any], gsc: dict[str, Any], access: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    jobs.extend(_search_query_answer_jobs(gsc))
    jobs.extend(_affiliate_product_article_jobs(access))
    jobs.extend(_hub_article_jobs(gsc))
    jobs.extend(_buzblogger_jobs(gsc))
    return sorted(jobs, key=lambda row: (int(row["priority"]), row["kind"], row["id"]))


def write_improvement_jobs(
    config: dict[str, Any],
    gsc: dict[str, Any],
    access: dict[str, Any],
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = generate_improvement_jobs(config, gsc, access)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "proposal",
        "note": "kdeck should convert accepted jobs into Goal Queue items; rqdb4ai executes app-owned job functions.",
        "jobs": jobs,
    }
    latest = out_dir / "improvement_jobs_latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    history = out_dir / f"improvement_jobs_{datetime.now().strftime('%Y%m%d')}.json"
    history.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    return latest


def _amazon_cta_jobs(access: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def _search_query_answer_jobs(gsc: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in gsc.get("boost_queries", [])[:20]:
        query = str(row.get("query") or "").strip()
        page = str(row.get("page") or "").strip()
        if not query or not page:
            continue
        if "/lp.php" in page:
            continue
        if row.get("impressions", 0) < 10:
            continue
        if not (8 <= float(row.get("position") or 0) <= 30):
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        job = _base_job(
            "search_query_answer_article",
            f"検索意図回答記事を作る: {query}",
            10,
            "aixec",
            "enqueue:search_query_answer_article",
            {
                "query": query,
                "page": page,
                "position": row.get("position", 0),
                "impressions": row.get("impressions", 0),
                "clicks": row.get("clicks", 0),
                "preferred_affiliate": "amazon",
            },
        )
        job["success_rule"] = "A search-intent article is published to AIxSNS with an internal link to the ranked page and Amazon-first affiliate CTA."
        job["cooldown_minutes"] = 120
        job["max_attempts_per_day"] = 1
        jobs.append(job)
        if len(jobs) >= 10:
            break
    return jobs


def _affiliate_product_article_jobs(access: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in access.get("top_affiliate_products", [])[:30]:
        product = str(row.get("product") or "").strip()
        if not product or product == "(unknown)" or product.lower() == "test":
            continue
        clicks = int(row.get("clicks") or 0)
        if clicks < 3:
            continue
        key = (str(row.get("pid") or ""), str(row.get("jan") or ""), str(row.get("model") or ""), product.lower())
        digest = "|".join(key)
        if digest in seen:
            continue
        seen.add(digest)
        job = _base_job(
            "affiliate_product_article",
            f"実クリック商品記事を作る: {product[:48]}",
            20,
            "aixec",
            "enqueue:affiliate_product_article",
            {
                "product": product,
                "pid": row.get("pid", ""),
                "jan": row.get("jan", ""),
                "asin": row.get("asin", ""),
                "model": row.get("model", ""),
                "source": row.get("from", ""),
                "to": row.get("to", ""),
                "clicks": clicks,
                "raw_clicks": row.get("raw_clicks", 0),
                "preferred_affiliate": "amazon",
            },
        )
        job["success_rule"] = "A product-focused AIxSNS article is published for a product with real human affiliate clicks, linking to Amazon first and the source page."
        job["cooldown_minutes"] = 180
        job["max_attempts_per_day"] = 1
        jobs.append(job)
        if len(jobs) >= 8:
            break
    return jobs


def _hub_article_jobs(gsc: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    amazon_topics = ("python", "linux", "プログラミング", "生成ai", "gemini", "ipad")
    for row in gsc.get("hub_topics", [])[:30]:
        topic = str(row.get("topic", ""))
        if not topic:
            continue
        topic_l = topic.lower()
        if len(topic_l) <= 2 or topic_l in {"ai", "書籍", "reviews", "or", "()"}:
            continue
        if not any(key in topic_l for key in amazon_topics):
            continue
        normalized = topic_l.replace("　", " ").strip()
        normalized = {
            "linux": "linux",
            "linuxサーバー": "linux",
            "ipad": "ipad",
        }.get(normalized, normalized)
        if normalized in seen_topics:
            continue
        seen_topics.add(normalized)
        job = _base_job(
            "amazon_hub_article",
            f"Amazon向けハブ記事を作る: {topic}",
            30,
            "aixec",
            "enqueue:aixec_hub_article_from_gsc",
            {
                "topic": topic,
                "queries": row.get("queries", 0),
                "impressions": row.get("impressions", 0),
                "intent": "comparison/buying-guide",
                "preferred_affiliate": "amazon",
            },
        )
        job["success_rule"] = "Hub article is published, indexed, and links to Amazon-first product/AIxTube pages."
        job["cooldown_minutes"] = 240
        jobs.append(job)
    return jobs


def _aixtube_jobs(gsc: dict[str, Any], access: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def _buzblogger_jobs(gsc: dict[str, Any]) -> list[dict[str, Any]]:
    if not gsc.get("boost_queries"):
        return []
    job = _base_job(
        "buzblogger_search_intent",
        "BuzBloggerを検索クエリ回答型に寄せる",
        40,
        "buzblogger",
        "enqueue:buzblogger_search_intent_tuning",
        {
            "sample_queries": [row.get("query", "") for row in gsc.get("boost_queries", [])[:10]],
            "preferred_affiliate": "amazon",
        },
    )
    job["success_rule"] = "Generated articles include search_query, answer practical intent, and select products by theme text."
    job["cooldown_minutes"] = 360
    return [job]
