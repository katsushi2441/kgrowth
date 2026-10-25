#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""このマシン（xb-rtx3090-1）の nginx アクセスログを日ごとに保管し、外部からの PHP 狙いのアクセスを数える。

**なぜ作ったか（2026-10-25）。** 高市総理の PHP2Shell の周知（10/21 21:55）のあとに攻撃が増えたかを調べようとしたら、
nginx のログは logrotate で14日しか残らず、heteml には今回の期間のアクセスログが無かった。次に同じことが起きたときに
「周知の前後」を比べられるよう、毎日 /mnt/data に日別の gz で残し、数えた結果を reports/ に書く。

- 保管先: /mnt/data/weblogs/xb-rtx3090-1/nginx/YYYY-MM-DD.log.gz（その日の行を重ねずにまとめる。今日の分は翌日に確定）
- 数える: 外部（自社・heteml・LAN を除く）の全件・.php を狙ったもの・.php への POST・IP の数・いちばん多いIPの件数
- PHP2Shell は「大きな POST を任意の .php へ」送る攻撃でアプリのログには残らない（Datadog）。いまの combined 形式には
  リクエストの大きさが無いので、件数までしか分からない。nginx の log_format に $request_length を足すと大きさも数えられる。

  /usr/bin/python3 -m kgrowth.weblog_archive            # 保管して数える
  kdeck ゴール kgrowth-weblog-archive（1日1回）は archive_job を呼ぶ
"""
from __future__ import annotations

import collections
import datetime
import glob
import gzip
import json
import os
import re

SRC_GLOB = "/var/log/nginx/access.log*"
DEST = "/mnt/data/weblogs/xb-rtx3090-1/nginx"
# 詳細ログ（deploy/nginx/00-kgrowth-detail-log.conf を入れると出る。大きさ rl= 付き）は別の置き場に保管する
DETAIL_GLOB = "/var/log/nginx/access_detail.log*"
DETAIL_DEST = "/mnt/data/weblogs/xb-rtx3090-1/nginx_detail"
BIG_POST = 100_000  # これより大きい .php への POST を「大きな POST」として数える（PHP2Shell の見分け）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_MD = os.path.join(ROOT, "reports", "attack_timeline_latest.md")
REPORT_JSON = os.path.join(ROOT, "data", "attack_timeline_latest.json")
# 自社の経路（LAN・ローカル・heteml の中継・自社回線）は数えない
INTERNAL = ("192.168.", "127.", "157.7.188.210", "60.120.193.111")
LINE = re.compile(r'^(\S+) \S+ \S+ \[(\d{2}/\w{3}/\d{4}):(\d{2}):\d{2}:\d{2} [^\]]+\] "(\S+) (\S+)')


def _open(path: str):
    return gzip.open(path, "rt", errors="replace") if path.endswith(".gz") else open(path, errors="replace")


def _day(s: str) -> str:
    return datetime.datetime.strptime(s, "%d/%b/%Y").strftime("%Y-%m-%d")


def archive(src_glob: str = SRC_GLOB, dest: str = DEST) -> list[str]:
    """/var/log/nginx の全世代を読み、昨日までの日を日別ファイルにまとめる。既にある日は行を足すだけ（重ねない）。"""
    by_day: dict[str, set[str]] = collections.defaultdict(set)
    for p in glob.glob(src_glob):
        with _open(p) as f:
            for line in f:
                m = LINE.match(line)
                if m:
                    by_day[_day(m.group(2))].add(line if line.endswith("\n") else line + "\n")
    if not by_day:
        return []
    os.makedirs(dest, exist_ok=True)
    today = datetime.date.today().strftime("%Y-%m-%d")
    written = []
    for day, lines in sorted(by_day.items()):
        if day >= today:
            continue
        out = os.path.join(dest, f"{day}.log.gz")
        old: set[str] = set()
        if os.path.exists(out):
            with gzip.open(out, "rt", errors="replace") as f:
                old = set(f)
        if lines <= old:
            continue
        merged = sorted(old | lines, key=lambda l: (LINE.match(l).group(3) if LINE.match(l) else "", l))
        tmp = out + ".tmp"
        with gzip.open(tmp, "wt") as f:
            f.writelines(merged)
        os.replace(tmp, out)
        written.append(day)
    return written


def count(days: int = 60) -> dict:
    """保管した日別ファイル＋今日のログから、外部アクセスと PHP 狙いを日ごと・時間ごとに数える。"""
    files = sorted(glob.glob(os.path.join(DEST, "*.log.gz")))[-days:]
    lines: set[str] = set()
    for p in files:
        with gzip.open(p, "rt", errors="replace") as f:
            lines.update(f)
    today = datetime.date.today().strftime("%Y-%m-%d")
    for p in glob.glob(SRC_GLOB):
        with _open(p) as f:
            lines.update(l for l in f if (m := LINE.match(l)) and _day(m.group(2)) == today)
    daily: dict[str, dict] = {}
    hourly: collections.Counter = collections.Counter()
    for line in lines:
        m = LINE.match(line)
        if not m:
            continue
        ip, d, hour, meth, path = m.groups()
        if ip.startswith(INTERNAL):
            continue
        day = _day(d)
        r = daily.setdefault(day, {"external": 0, "php": 0, "php_post": 0, "php_big_post": None, "ips": collections.Counter()})
        r["external"] += 1
        if ".php" in path.lower():
            r["php"] += 1
            r["ips"][ip] += 1
            hourly[f"{day} {hour}"] += 1
            if meth == "POST":
                r["php_post"] += 1
    # 詳細ログがある日は、.php への大きな POST（rl= が BIG_POST 超）を数える
    big: collections.Counter = collections.Counter()
    seen_detail: set[str] = set()
    for p in sorted(glob.glob(os.path.join(DETAIL_DEST, "*.log.gz")))[-days:] + glob.glob(DETAIL_GLOB):
        with _open(p) as f:
            for line in f:
                m = LINE.match(line)
                if not m or m.group(1).startswith(INTERNAL) or line in seen_detail:
                    continue
                seen_detail.add(line)
                day = _day(m.group(2))
                big[day] += 0
                rl = re.search(r" rl=(\d+)", line)
                if m.group(4) == "POST" and ".php" in m.group(5).lower() and rl and int(rl.group(1)) > BIG_POST:
                    big[day] += 1
    for day, n in big.items():
        if day in daily:
            daily[day]["php_big_post"] = n
    rows = []
    for day in sorted(daily):
        r = daily[day]
        top = r["ips"].most_common(1)
        rows.append({"day": day, "external": r["external"], "php": r["php"], "php_post": r["php_post"],
                     "php_big_post": r["php_big_post"], "php_ips": len(r["ips"]), "top_ip": top[0][0] if top else "", "top_ip_php": top[0][1] if top else 0})
    return {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"), "source": DEST,
            "daily": rows, "php_hourly": dict(sorted(hourly.items()))}


def write_report(res: dict) -> None:
    os.makedirs(os.path.dirname(REPORT_JSON), exist_ok=True)
    os.makedirs(os.path.dirname(REPORT_MD), exist_ok=True)
    with open(REPORT_JSON, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    out = [f"# 外部からの PHP 狙いのアクセス（xb-rtx3090-1 の nginx・{res['generated_at']}）", "",
           "自社・heteml・LAN の経路は除く。PHP 狙い＝パスに .php を含むもの。いちばん多いIPが大半なら、1台のスキャンです。", ""]
    for r in res["daily"]:
        share = f"・最多IP {r['top_ip']} が {r['top_ip_php']}件" if r["php"] else ""
        bigs = f"・大きなPOST {r['php_big_post']}件" if r.get("php_big_post") is not None else ""
        out.append(f"- {r['day']}: 外部 {r['external']}件 / PHP狙い {r['php']}件（POST {r['php_post']}件{bigs}・IP {r['php_ips']}個{share}）")
    with open(REPORT_MD, "w") as f:
        f.write("\n".join(out) + "\n")


def archive_job(**_kw) -> dict:
    """kdeck ゴール kgrowth-weblog-archive。保管した日数を items にする（新しい日が無ければ 0）。"""
    written = archive()
    archive(DETAIL_GLOB, DETAIL_DEST)
    res = count()
    write_report(res)
    if not os.path.exists(os.path.join(DEST, f"{(datetime.date.today() - datetime.timedelta(days=1)):%Y-%m-%d}.log.gz")):
        raise RuntimeError("昨日の分が保管されていない（/var/log/nginx が読めない、または昨日のアクセスが0件）")
    return {"items": len(written), "result": {"written": written, "days": len(res["daily"])}}


if __name__ == "__main__":
    w = archive()
    archive(DETAIL_GLOB, DETAIL_DEST)
    res = count()
    write_report(res)
    print("保管した日:", w)
    print(open(REPORT_MD).read())
