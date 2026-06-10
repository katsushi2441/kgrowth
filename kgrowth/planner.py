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
    lines: list[str] = []

    lines.extend(
        [
            "# AIxEC / AIxSNS / AIxTube アクセス改善プラン",
            "",
            f"生成日: {today}",
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
            f"- access.log総リクエスト: {_fmt_int(access.get('total_requests', 0))}",
            f"- access.logユニークIP: {_fmt_int(access.get('unique_ips', 0))}",
            f"- bot比率: {access.get('bot_ratio', 0) * 100:.1f}%",
            "",
            "---",
            "",
            "## 改善1: 検索クエリ起点のBuzBlogger修正（最優先）",
            "",
            "問題: バズそのものを説明する記事は検索需要とずれやすい。",
            "解決: GSCとaccess.logの検索語から、実際の検索クエリに答える記事へ寄せる。",
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
            "- `search_query` を記事生成の中心に置く。",
            "- `buzz_summary` は本文末尾の参考情報に降格する。",
            "- 商品選定は記事テーマの自由テキスト検索を優先する。",
            "",
            "---",
            "",
            "## 改善2: 重複登録ログのnoindex",
            "",
            "問題: register投稿は同型文が増えやすく、検索面では低品質ページ群になりやすい。",
            "解決: 単一register投稿ページだけ `noindex,follow` にする。SNS一覧や実用記事には適用しない。",
            "",
            "### 確認観点",
            "",
            "- `author=register` の詳細ページだけ noindex。",
            "- BuzBloggerや通常投稿は index 対象のまま。",
            "",
            "---",
            "",
            "## 改善3: ハブ記事ジェネレーター",
            "",
            "問題: 商品ページ単体では楽天・Amazonの商品ページに勝ちにくい。",
            "解決: GSCで表示があるクエリクラスタから、比較・選び方・おすすめ記事を生成する。",
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
            "- 商品DBの登録数ではなく、GSCで表示があるテーマを優先する。",
            "- ハブ記事から商品ページ・AIxTube動画・ランキングへ内部リンクする。",
            "- 週次で順位とクリック変化を追跡する。",
            "",
            "---",
            "",
            "## 改善4: AIxTube / YouTube 配信候補",
            "",
            "問題: サイト内動画だけでは新規流入が限定される。",
            "解決: 品質条件を満たす動画をYouTube配信候補にする。商品説明なし・IDのみ動画は除外する。",
            "",
            "### access.log上のAIxTube状況",
            "",
            f"- AIxTube系リクエスト: {_fmt_int(access.get('page_types', {}).get('aixtube', 0))}",
            "- 動画生成ログと商品説明の有無を照合して、低品質動画は削除・再生成対象にする。",
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
