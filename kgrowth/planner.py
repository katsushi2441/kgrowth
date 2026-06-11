from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _fmt_int(value: int | float) -> str:
    return f"{int(value):,}"


def _table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], limit: int) -> list[str]:
    lines = ["| " + " | ".join(label for label, _ in columns) + " |"]
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows[:limit]:
        lines.append("| " + " | ".join(str(row.get(key, "")) for _, key in columns) + " |")
    if not rows:
        lines.append("| " + " | ".join(["なし"] + [""] * (len(columns) - 1)) + " |")
    return lines


def generate_plan(
    config: dict[str, Any],
    gsc: dict[str, Any],
    access: dict[str, Any],
    efficiency: dict[str, Any],
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%Y%m%d")
    max_rows = int(config.get("analysis", {}).get("max_rows", 40))
    site_name = str(config.get("site_name") or config.get("domain_id") or config.get("site_url") or "Site")
    is_kurage = config.get("growth_profile") == "kurage"
    lines: list[str] = []

    lines.extend(
        [
            f"# {site_name} アクセス改善プラン",
            "",
            f"生成日: {today}",
            f"対象サイト: {config.get('site_url', '')}",
            "",
            "## Context",
            "",
        ]
    )
    if gsc.get("available"):
        lines.extend(
            [
                f"- GSC対象期間: {gsc.get('start')} 〜 {gsc.get('end')}",
                f"- 表示回数: {_fmt_int(gsc.get('total_impressions', 0))}",
                f"- クリック: {_fmt_int(gsc.get('total_clicks', 0))}",
                f"- CTR: {gsc.get('ctr', 0) * 100:.2f}%",
                f"- 表示クエリ数: {_fmt_int(gsc.get('queries', 0))}",
            ]
        )
        if efficiency.get("indexed_pages_estimate"):
            lines.append(
                f"- 推定インデックスページあたり表示回数: {efficiency.get('impressions_per_page_rounded')}/期間"
            )
    else:
        lines.append("- GSCデータ未取得。`fetch-gsc` 実行後に再生成する。")
    lines.extend(
        [
            f"- simpletrack実PV: {_fmt_int(access.get('total_requests', 0))}",
            f"- simpletrack rawリクエスト: {_fmt_int(access.get('raw_requests', access.get('total_requests', 0)))}",
            f"- simpletrack実ユニークIP: {_fmt_int(access.get('unique_ips', 0))}",
            f"- bot比率: {access.get('bot_ratio', 0) * 100:.1f}%",
            "",
            "---",
            "",
            "## 改善1: 検索クエリ起点のコンテンツ改善（最優先）",
            "",
            "問題: 検索表示があるのに、ページ内容・タイトル・説明が検索意図に寄り切っていない。",
            "解決: GSCとaccess.logの検索語から、実際の検索クエリに答えるページへ寄せる。",
            "",
            "### 実行候補クエリ",
            "",
        ]
    )
    lines.extend(
        _table(
            gsc.get("boost_queries", []),
            [("クエリ", "query"), ("順位", "position"), ("表示", "impressions"), ("対象URL", "page")],
            min(20, max_rows),
        )
    )
    lines.extend(
        [
            "",
            "### 実装方針",
            "",
            "- `search_query` を改善作業の中心に置く。",
            "- ページタイトル、description、内部リンク、CTAを検索意図に合わせる。",
            "- Amazon導線がある場合は、検索意図と一致するキーワード/ASINだけを使う。",
            "",
            "---",
            "",
            "## 改善2: 低品質・重複ページの整理",
            "",
            "問題: 自動生成ページは同型文が増えやすく、検索面では低品質ページ群になりやすい。",
            "解決: 検索流入を狙うページと、一覧/補助ページを分け、必要なら `noindex,follow` を適用する。",
            "",
            "### 確認観点",
            "",
            "- 検索流入を狙う詳細ページは index 対象のままにする。",
            "- 重複・管理・一時ページは noindex 候補にする。",
            "",
            "---",
            "",
            "## 改善3: ハブ/一覧ページ改善",
            "",
            "問題: 詳細ページ単体では検索意図を広く受けきれない。",
            "解決: GSCで表示があるクエリクラスタから、一覧・ハブ・関連記事導線を作る。",
            "",
            "### ハブ記事候補",
            "",
        ]
    )
    lines.extend(
        _table(
            gsc.get("hub_topics", []),
            [("テーマ語", "topic"), ("関連クエリ数", "queries"), ("合計表示", "impressions")],
            min(25, max_rows),
        )
    )
    lines.extend(
        [
            "",
            "### 実装方針",
            "",
            "- 登録数ではなく、GSCで表示があるテーマを優先する。",
            "- ハブ/一覧から動画詳細・関連ページ・Amazon CTAへ内部リンクする。",
            "- 週次で順位とクリック変化を追跡する。",
            "",
            "---",
            "",
            "## 改善4: 動画配信・動画SEO候補",
            "",
            "問題: サイト内動画だけでは新規流入が限定される。",
            "解決: 品質条件を満たす動画をYouTube配信・動画サイトマップ・関連導線の改善候補にする。",
            "",
            "### access.log上の動画状況",
            "",
            f"- 動画系リクエスト: {_fmt_int(access.get('page_types', {}).get('video', 0) if is_kurage else access.get('page_types', {}).get('aixtube', 0))}",
            "- 動画タイトル、説明、サムネイル、関連リンク、Amazon CTAを照合して改善対象を決める。",
            "",
            "---",
            "",
            "## Affiliate Findings",
            "",
            "simpletrackのbot除外・実クリック判定に基づく集計。`raw_clicks` はbot除外後のgo.php到達、`clicks` は実クリック判定済み。",
            "",
            "### Amazon / 楽天 実クリック",
            "",
            "| 対象 | 実クリック | rawクリック |",
            "|---|---:|---:|",
        ]
    )
    affiliate = access.get("affiliate_clicks", {})
    for target in ("amazon", "rakuten", "(unknown)"):
        if target in affiliate:
            row = affiliate[target]
            lines.append(f"| {target} | {_fmt_int(row.get('clicks', 0))} | {_fmt_int(row.get('raw_clicks', 0))} |")
    if not affiliate:
        lines.append("| なし | 0 | 0 |")
    lines.extend(
        [
            "",
            "### 実クリック上位の商品",
            "",
        ]
    )
    lines.extend(
        _table(
            access.get("top_affiliate_products", []),
            [("対象", "to"), ("商品", "product"), ("実クリック", "clicks"), ("raw", "raw_clicks"), ("流入元", "from")],
            20,
        )
    )
    lines.extend(
        [
            "",
            "### 実クリック上位の流入元",
            "",
        ]
    )
    lines.extend(
        _table(
            access.get("top_affiliate_sources", []),
            [("対象", "to"), ("流入元", "from"), ("実クリック", "clicks"), ("raw", "raw_clicks")],
            20,
        )
    )
    lines.extend(
        [
            "",
            "---",
            "",
            "## Access Log Findings",
            "",
            "### ページタイプ",
            "",
        ]
    )
    page_type_rows = [
        {"type": key, "requests": value} for key, value in access.get("page_types", {}).items()
    ]
    lines.extend(_table(page_type_rows, [("タイプ", "type"), ("リクエスト", "requests")], 20))
    lines.extend(["", "### 404上位", ""])
    not_found_rows = [
        {"path": key, "requests": value} for key, value in access.get("top_404", {}).items()
    ]
    lines.extend(_table(not_found_rows, [("パス", "path"), ("回数", "requests")], 20))
    lines.extend(
        [
            "",
            "---",
            "",
            "## 今週の実行順",
            "",
            "1. GSCの強化候補クエリから、BuzBloggerの生成仕様を検索意図型に寄せる。",
            "2. register投稿詳細ページのnoindexを確認・反映する。",
            "3. ハブ記事候補の上位テーマから、1〜3本だけ生成してGSC変化を見る。",
            "4. AIxTube動画は品質フィルタを通したものだけ外部配信候補にする。",
            "",
            "## 次週の比較",
            "",
            "- 表示回数、CTR、11〜30位クエリの上昇数を見る。",
            "- access.logで404、bot比率、実ユーザー流入ページを比較する。",
            "- 成果が出た生成仕様をkdeck Goal Queueへ昇格する。",
            "",
        ]
    )
    out = out_dir / f"growth_plan_{stamp}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    latest = out_dir / "growth_plan_latest.md"
    latest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    return out
