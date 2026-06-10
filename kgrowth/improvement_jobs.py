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
    jobs.extend(_amazon_cta_jobs(access))
    jobs.extend(_hub_article_jobs(gsc))
    jobs.extend(_aixtube_jobs(gsc, access))
    jobs.extend(_buzblogger_jobs(gsc))
    jobs.append(_noindex_register_job())
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


def _hub_article_jobs(gsc: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    amazon_topics = ("python", "linux", "ai", "プログラミング", "書籍", "生成ai", "gemini", "ipad")
    for row in gsc.get("hub_topics", [])[:30]:
        topic = str(row.get("topic", ""))
        if not topic:
            continue
        topic_l = topic.lower()
        if not any(key in topic_l for key in amazon_topics):
            continue
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
    jobs: list[dict[str, Any]] = []
    for row in gsc.get("boost_queries", [])[:20]:
        page = str(row.get("page", ""))
        if "aixtube.php" not in page:
            continue
        job = _base_job(
            "aixtube_search_snippet",
            f"検索表示があるAIxTubeページを改善: {row.get('query', '')}",
            35,
            "aixec",
            "enqueue:aixtube_search_page_improve",
            {
                "query": row.get("query", ""),
                "page": page,
                "position": row.get("position", 0),
                "impressions": row.get("impressions", 0),
                "preferred_affiliate": "amazon",
            },
        )
        job["success_rule"] = "Title/description/body/CTA are updated for the query and Amazon-first affiliate tracking remains active."
        jobs.append(job)
    return jobs


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


def _noindex_register_job() -> dict[str, Any]:
    job = _base_job(
        "aixsns_register_noindex",
        "AIxSNS register投稿詳細のnoindexを確認する",
        50,
        "aixec",
        "enqueue:aixsns_register_noindex_check",
        {
            "author": "register",
            "rule": "detail pages only: noindex,follow",
        },
    )
    job["success_rule"] = "register detail pages have noindex,follow; normal article pages remain indexable."
    job["cooldown_minutes"] = 1440
    job["max_attempts_per_day"] = 1
    return job
