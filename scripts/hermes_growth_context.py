#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


KGROWTH_ROOT = Path(__file__).resolve().parents[1]
KDECK_ROOT = Path("/home/kojima/work/kdeck")
PLAN = KGROWTH_ROOT / "reports" / "growth_plan_latest.md"
JOBS = KGROWTH_ROOT / "data" / "improvement_jobs_latest.json"


def run_json(command: list[str], cwd: Path) -> dict:
    try:
        proc = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, timeout=60)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "returncode": proc.returncode, "stderr": proc.stderr[-2000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_json", "stdout_tail": proc.stdout[-2000:]}


def load_jobs(limit: int = 38) -> dict:
    if not JOBS.is_file():
        return {"exists": False, "count": 0, "jobs": []}
    try:
        payload = json.loads(JOBS.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"exists": True, "error": str(exc), "count": 0, "jobs": []}
    jobs = payload.get("jobs", [])
    compact = []
    for job in jobs[:limit]:
        if not isinstance(job, dict):
            continue
        compact.append({
            "id": job.get("id"),
            "kind": job.get("kind"),
            "title": job.get("title"),
            "priority": job.get("priority"),
            "target_app": job.get("target_app"),
            "success_rule": job.get("success_rule"),
        })
    return {"exists": True, "count": len(jobs), "jobs": compact}


def plan_excerpt(limit: int = 1000) -> str:
    if not PLAN.is_file():
        return ""
    return PLAN.read_text(encoding="utf-8", errors="replace")[:limit]


def domain_context(limit: int = 16) -> list[dict]:
    out: list[dict] = []
    for domain_dir in sorted((KGROWTH_ROOT / "data" / "domains").glob("*")):
        if not domain_dir.is_dir():
            continue
        jobs_path = domain_dir / "improvement_jobs_latest.json"
        analysis_path = domain_dir / "analysis_latest.json"
        reports_path = KGROWTH_ROOT / "reports" / "domains" / domain_dir.name / "growth_plan_latest.md"
        jobs = []
        job_count = 0
        if jobs_path.is_file():
            try:
                payload = json.loads(jobs_path.read_text(encoding="utf-8"))
                all_jobs = payload.get("jobs", [])
                job_count = len(all_jobs)
                for job in all_jobs[:limit]:
                    jobs.append({
                        "id": job.get("id"),
                        "kind": job.get("kind"),
                        "title": job.get("title"),
                        "priority": job.get("priority"),
                        "target_app": job.get("target_app"),
                        "action": job.get("action"),
                    })
            except Exception:
                pass
        analysis_summary = {}
        if analysis_path.is_file():
            try:
                analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
                analysis_summary = {
                    "gsc": {
                        "available": (analysis.get("gsc") or {}).get("available"),
                        "impressions": (analysis.get("gsc") or {}).get("total_impressions"),
                        "clicks": (analysis.get("gsc") or {}).get("total_clicks"),
                    },
                    "access": {
                        "total_requests": (analysis.get("access") or {}).get("total_requests"),
                        "page_types": (analysis.get("access") or {}).get("page_types"),
                    },
                }
            except Exception:
                pass
        out.append({
            "domain": domain_dir.name,
            "job_count": job_count,
            "jobs": jobs,
            "analysis": analysis_summary,
            "plan_excerpt": reports_path.read_text(encoding="utf-8", errors="replace")[:800] if reports_path.is_file() else "",
        })
    return out


def main() -> None:
    status = run_json(["python3", "-m", "app.commander_tool", "status"], KDECK_ROOT)
    goals = status.get("goals", []) if isinstance(status, dict) else []
    kgrowth_goals = [goal for goal in goals if str(goal.get("goal_name", "")).startswith("kgrowth-")]
    status_counts: dict[str, int] = {}
    for goal in kgrowth_goals:
        key = str(goal.get("status") or "")
        status_counts[key] = status_counts.get(key, 0) + 1

    payload = {
        "kgrowth": {
            "repo": str(KGROWTH_ROOT),
            "improvement_jobs": load_jobs(),
            "plan_excerpt": plan_excerpt(),
            "domains": domain_context(),
        },
        "kdeck_goal_queue": {
            "summary": status.get("summary") if isinstance(status, dict) else {},
            "kgrowth_goal_count": len(kgrowth_goals),
            "kgrowth_status_counts": status_counts,
            "kgrowth_goals": [
                {
                    "goal_name": goal.get("goal_name"),
                    "status": goal.get("status"),
                    "next_action": goal.get("next_action"),
                    "next_reason": goal.get("next_reason"),
                    "today": goal.get("today"),
                    "current_job_id": goal.get("current_job_id"),
                    "last_note": goal.get("last_note") or goal.get("last_run_note"),
                }
                for goal in kgrowth_goals[:38]
            ],
            "events": status.get("events", [])[:5] if isinstance(status, dict) else [],
        },
        "recommended_commands": [
            "cd /home/kojima/work/kgrowth && python3 -m kgrowth.cli weekly --config config.json",
            "cd /home/kojima/work/kdeck && python3 -m app.commander_tool growth-cycle",
        ],
        "notes": [
            "Commander lives in kgrowth.",
            "kdeck is the Goal Queue state store and UI.",
            "Operate only on kgrowth-* goals.",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
