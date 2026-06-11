from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _job_id(kind: str, payload: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _job_signature(kind: str, payload: dict[str, Any]) -> str:
    return _job_id(kind, payload)


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


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _semantic_key(kind: str, payload: dict[str, Any]) -> str:
    if kind == "search_query_answer_article":
        return f"{kind}|query={_norm(payload.get('query'))}|page={_norm(payload.get('page'))}"
    if kind == "affiliate_product_article":
        return "|".join(
            [
                kind,
                f"pid={_norm(payload.get('pid'))}",
                f"jan={_norm(payload.get('jan'))}",
                f"model={_norm(payload.get('model'))}",
                f"product={_norm(payload.get('product'))}",
            ]
        )
    if kind == "amazon_hub_article":
        return f"{kind}|topic={_norm(payload.get('topic'))}"
    if kind == "buzblogger_search_intent":
        return kind
    return f"{kind}|{_job_signature(kind, payload)}"


def _kdeck_controller_db(config: dict[str, Any]) -> Path:
    value = (
        os.environ.get("KGROWTH_KDECK_CONTROLLER_DB")
        or os.environ.get("KDECK_CONTROLLER_DB")
        or config.get("kdeck_controller_db")
        or "/home/kojima/work/kdeck/storage/controller.sqlite"
    )
    return Path(str(value)).expanduser()


def completed_improvement_keys(config: dict[str, Any]) -> dict[str, set[str]]:
    db_path = _kdeck_controller_db(config)
    completed = {"ids": set(), "signatures": set(), "semantic": set(), "goal_names": set(), "titles": set()}
    if not db_path.is_file():
        return completed
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT goals.goal_name, goals.payload, goal_runs.note
            FROM goal_runs
            JOIN goals ON goals.id = goal_runs.goal_id
            WHERE goals.goal_name LIKE 'kgrowth-%'
              AND (goal_runs.ok = 1 OR goal_runs.business_status = 'ok')
            """
        ).fetchall()
    except sqlite3.Error:
        return completed
    finally:
        if conn is not None:
            conn.close()
    for row in rows:
        completed["goal_names"].add(str(row["goal_name"] or ""))
        note = str(row["note"] or "").split(":", 1)[0].strip().lower()
        if note:
            completed["titles"].add(note)
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except json.JSONDecodeError:
            continue
        improvement_job = (((payload.get("kwargs") or {}).get("improvement_job")) or {})
        if not isinstance(improvement_job, dict):
            continue
        job_id = str(improvement_job.get("id") or "").strip()
        kind = str(improvement_job.get("kind") or "").strip()
        job_payload = improvement_job.get("payload") if isinstance(improvement_job.get("payload"), dict) else {}
        title = str(improvement_job.get("title") or "").strip().lower()
        if job_id:
            completed["ids"].add(job_id)
        if kind and job_payload:
            completed["signatures"].add(_job_signature(kind, job_payload))
            completed["semantic"].add(_semantic_key(kind, job_payload))
        if title:
            completed["titles"].add(title)
    return completed


def _is_completed_job(job: dict[str, Any], completed: dict[str, set[str]]) -> bool:
    job_id = str(job.get("id") or "").strip()
    kind = str(job.get("kind") or "").strip()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    title = str(job.get("title") or "").strip().lower()
    title_key = title.split(":", 1)[-1].strip() if ":" in title else title
    return (
        bool(job_id and job_id in completed["ids"])
        or bool(kind and payload and _job_signature(kind, payload) in completed["signatures"])
        or bool(kind and payload and _semantic_key(kind, payload) in completed["semantic"])
        or bool(title_key and title_key in completed["titles"])
    )


def generate_improvement_jobs(config: dict[str, Any], gsc: dict[str, Any], access: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if config.get("growth_profile") == "kurage":
        jobs.extend(_kurage_search_video_jobs(config, gsc))
        jobs.extend(_kurage_amazon_cta_jobs(config, access))
        jobs.extend(_kurage_video_seo_jobs(config, access))
    else:
        jobs.extend(_search_query_answer_jobs(gsc))
        jobs.extend(_affiliate_product_article_jobs(access))
        jobs.extend(_hub_article_jobs(gsc))
        jobs.extend(_buzblogger_jobs(gsc))
    completed = completed_improvement_keys(config)
    fresh_jobs = [job for job in jobs if not _is_completed_job(job, completed)]
    return sorted(fresh_jobs, key=lambda row: (int(row["priority"]), row["kind"], row["id"]))


def write_improvement_jobs(
    config: dict[str, Any],
    gsc: dict[str, Any],
    access: dict[str, Any],
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    completed = completed_improvement_keys(config)
    jobs = generate_improvement_jobs(config, gsc, access)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "proposal",
        "note": "kdeck converts fresh kgrowth jobs into Goal Queue items; completed kgrowth jobs are never proposed again.",
        "completed_history": {
            "ids": len(completed["ids"]),
            "signatures": len(completed["signatures"]),
            "semantic": len(completed["semantic"]),
            "titles": len(completed["titles"]),
        },
        "jobs": jobs,
    }
    latest = out_dir / "improvement_jobs_latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    history = out_dir / f"improvement_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    history.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    return latest


def _amazon_cta_jobs(access: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def _domain_payload(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain_id": config.get("domain_id", ""),
        "site_name": config.get("site_name", ""),
        "site_url": config.get("site_url", ""),
    }


def _kurage_search_video_jobs(config: dict[str, Any], gsc: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    target_app = str(config.get("target_app") or "kurage")
    domain_payload = _domain_payload(config)
    seen: set[str] = set()
    for row in gsc.get("boost_queries", [])[:20]:
        query = str(row.get("query") or "").strip()
        page = str(row.get("page") or "").strip()
        if not query or not page:
            continue
        if row.get("impressions", 0) < 5:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        payload = {
            **domain_payload,
            "query": query,
            "page": page,
            "position": row.get("position", 0),
            "impressions": row.get("impressions", 0),
            "clicks": row.get("clicks", 0),
            "preferred_affiliate": "amazon",
        }
        job = _base_job(
            "kurage_search_intent_video_page",
            f"Kurage検索意図動画ページを改善: {query}",
            10,
            target_app,
            "enqueue:kurage_search_intent_video_page",
            payload,
        )
        job["success_rule"] = "Kurage video/list/detail page is improved for the query, with clearer title/description/internal links and an Amazon CTA when relevant."
        job["cooldown_minutes"] = 120
        job["max_attempts_per_day"] = 1
        jobs.append(job)
        if len(jobs) >= 10:
            break
    return jobs


def _kurage_amazon_cta_jobs(config: dict[str, Any], access: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    target_app = str(config.get("target_app") or "kurage")
    domain_payload = _domain_payload(config)
    seen: set[str] = set()
    for row in access.get("top_affiliate_products", [])[:30]:
        product = str(row.get("product") or "").strip()
        if not product or product == "(unknown)":
            continue
        clicks = int(row.get("clicks") or 0)
        raw_clicks = int(row.get("raw_clicks") or 0)
        if raw_clicks < 1:
            continue
        key = f"{product.lower()}|{row.get('asin','')}|{row.get('from','')}"
        if key in seen:
            continue
        seen.add(key)
        payload = {
            **domain_payload,
            "keyword": product,
            "asin": row.get("asin", ""),
            "source_page": row.get("from", ""),
            "clicks": clicks,
            "raw_clicks": raw_clicks,
            "preferred_affiliate": "amazon",
        }
        job = _base_job(
            "kurage_amazon_cta_from_clicks",
            f"Kurage Amazon CTAを改善: {product[:48]}",
            20,
            target_app,
            "enqueue:kurage_amazon_cta_from_clicks",
            payload,
        )
        job["success_rule"] = "The source Kurage page keeps or improves a relevant Amazon CTA and future similar videos inherit the same CTA pattern."
        job["cooldown_minutes"] = 180
        job["max_attempts_per_day"] = 1
        jobs.append(job)
        if len(jobs) >= 8:
            break
    return jobs


def _kurage_video_seo_jobs(config: dict[str, Any], access: dict[str, Any]) -> list[dict[str, Any]]:
    top_pages = access.get("top_pages", {})
    candidates = []
    for page, count in top_pages.items():
        page_s = str(page)
        if ("kuragev.php" not in page_s and "horizonv.php" not in page_s) or "id=" not in page_s:
            continue
        candidates.append((page_s, int(count)))
    jobs: list[dict[str, Any]] = []
    target_app = str(config.get("target_app") or "kurage")
    domain_payload = _domain_payload(config)
    for page, count in candidates[:10]:
        payload = {**domain_payload, "page": page, "views": count}
        job = _base_job(
            "kurage_video_detail_seo",
            f"Kurage動画詳細SEOを改善: {page}",
            30,
            target_app,
            "enqueue:kurage_video_detail_seo",
            payload,
        )
        job["success_rule"] = "The high-view video detail page has stronger title, description, related links, video sitemap metadata, and relevant Amazon CTA."
        job["cooldown_minutes"] = 240
        job["max_attempts_per_day"] = 1
        jobs.append(job)
    return jobs


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
