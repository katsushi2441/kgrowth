<?php
/**
 * gsc_report.php — GSCデータ分析 & 改善指示書生成
 *
 * gsc_fetch.php の出力 (data/gsc_latest.json) を読み、
 * 改善指示書 (data/kaizen_YYYYMMDD.md) を生成する。
 *
 * 分析ロジック:
 *   A. タイトル改修候補   : 順位10位以内 × 表示あり × CTRが順位期待値の半分以下
 *   B. 強化候補（勝ち筋）  : 順位11〜30位 × 表示あり → 内部リンク・コンテンツ追加で1ページ目を狙える
 *   C. ハブ記事候補       : クエリの頻出語クラスタ → 検索需要が証明されたテーマ
 *   D. ページタイプ別診断  : /product/ vs sns.php vs その他、どのテンプレが稼いでいるか
 *
 * 実行: php gsc_report.php
 */

const DATA_FILE = __DIR__ . '/data/gsc_latest.json';
const OUT_DIR   = __DIR__ . '/data';

// 順位帯ごとの期待CTR（日本のSERP一般値の概算）
function expected_ctr(float $pos): float {
    if ($pos <= 1)  return 0.28;
    if ($pos <= 2)  return 0.15;
    if ($pos <= 3)  return 0.10;
    if ($pos <= 5)  return 0.06;
    if ($pos <= 10) return 0.025;
    return 0.005;
}

function page_type(string $url): string {
    if (str_contains($url, '/product'))        return '商品ページ';
    if (str_contains($url, 'sns.php'))         return 'SNS/記事';
    if (str_contains($url, 'ranking'))         return 'ランキング';
    if (str_contains($url, 'index.php'))       return '検索/ジャンル';
    if (rtrim(parse_url($url, PHP_URL_PATH) ?? '', '/') === '') return 'トップ';
    return 'その他';
}

// 日本語クエリの粗いトークン分割（スペース区切り + 型番抽出）
function tokenize(string $q): array {
    $tokens = preg_split('/[\s　]+/u', trim($q));
    $extra = [];
    foreach ($tokens as $t) {
        // 型番らしきもの（英数字混合）はそのまま重視
        if (preg_match('/^[A-Za-z0-9\-]{4,}$/', $t)) $extra[] = strtoupper($t);
    }
    return array_merge($tokens, $extra);
}

$data = json_decode(file_get_contents(DATA_FILE), true)
    or die("ERROR: 先に gsc_fetch.php を実行してください\n");

$qp    = $data['query_page'];
$pages = $data['pages'];

// ===== 集計 =====
$totalImp = 0; $totalClk = 0;
$byQuery = [];
foreach ($qp as $row) {
    [$query, $page] = $row['keys'];
    $totalImp += $row['impressions'];
    $totalClk += $row['clicks'];
    if (!isset($byQuery[$query])) {
        $byQuery[$query] = ['imp' => 0, 'clk' => 0, 'posSum' => 0, 'pages' => []];
    }
    $byQuery[$query]['imp']    += $row['impressions'];
    $byQuery[$query]['clk']    += $row['clicks'];
    $byQuery[$query]['posSum'] += $row['position'] * $row['impressions'];
    $byQuery[$query]['pages'][$page] = ($byQuery[$query]['pages'][$page] ?? 0) + $row['impressions'];
}
foreach ($byQuery as &$q) {
    $q['pos'] = $q['imp'] > 0 ? $q['posSum'] / $q['imp'] : 999;
    arsort($q['pages']);
}
unset($q);

// A. タイトル改修候補
$titleFix = [];
foreach ($byQuery as $query => $q) {
    if ($q['pos'] <= 10 && $q['imp'] >= 10) {
        $ctr = $q['imp'] ? $q['clk'] / $q['imp'] : 0;
        if ($ctr < expected_ctr($q['pos']) * 0.5) {
            $titleFix[$query] = $q + ['ctr' => $ctr];
        }
    }
}
uasort($titleFix, fn($a, $b) => $b['imp'] <=> $a['imp']);

// B. 強化候補（11〜30位）
$boost = [];
foreach ($byQuery as $query => $q) {
    if ($q['pos'] > 10 && $q['pos'] <= 30 && $q['imp'] >= 5) {
        $boost[$query] = $q;
    }
}
uasort($boost, fn($a, $b) => $b['imp'] <=> $a['imp']);

// C. ハブ記事候補（頻出語クラスタ）
$tokenStats = [];
foreach ($byQuery as $query => $q) {
    foreach (array_unique(tokenize($query)) as $t) {
        if (mb_strlen($t) < 2) continue;
        if (!isset($tokenStats[$t])) $tokenStats[$t] = ['imp' => 0, 'queries' => 0];
        $tokenStats[$t]['imp']     += $q['imp'];
        $tokenStats[$t]['queries'] += 1;
    }
}
$hub = array_filter($tokenStats, fn($t) => $t['queries'] >= 3);
uasort($hub, fn($a, $b) => $b['imp'] <=> $a['imp']);

// D. ページタイプ別
$byType = [];
foreach ($pages as $row) {
    $t = page_type($row['keys'][0]);
    if (!isset($byType[$t])) $byType[$t] = ['imp' => 0, 'clk' => 0, 'pages' => 0];
    $byType[$t]['imp']   += $row['impressions'];
    $byType[$t]['clk']   += $row['clicks'];
    $byType[$t]['pages'] += 1;
}
uasort($byType, fn($a, $b) => $b['imp'] <=> $a['imp']);

// ===== 指示書生成 =====
$md = [];
$md[] = "# AIxEC SEO改善指示書";
$md[] = "";
$md[] = "生成日: " . date('Y-m-d') . " ／ 対象期間: {$data['start']} 〜 {$data['end']} ／ プロパティ: {$data['site']}";
$md[] = "";
$md[] = "## 1. 現状サマリー";
$md[] = "";
$md[] = sprintf("- 表示回数合計: %s 回（%d日間）", number_format($totalImp), 28);
$md[] = sprintf("- クリック合計: %s 回（CTR %.2f%%）", number_format($totalClk), $totalImp ? $totalClk / $totalImp * 100 : 0);
$md[] = sprintf("- 表示の付いたクエリ数: %s", number_format(count($byQuery)));
$md[] = "";

$md[] = "## 2. ページタイプ別の稼働状況";
$md[] = "";
$md[] = "| タイプ | 表示ページ数 | 表示回数 | クリック |";
$md[] = "|---|---|---|---|";
foreach ($byType as $type => $t) {
    $md[] = sprintf("| %s | %s | %s | %s |", $type,
        number_format($t['pages']), number_format($t['imp']), number_format($t['clk']));
}
$md[] = "";
$md[] = "→ 表示が付いているタイプに生成リソースを寄せ、付いていないタイプの量産は停止する。";
$md[] = "";

$md[] = "## 3. 【優先度A】タイトル・description改修（即効・工数小）";
$md[] = "";
$md[] = "1ページ目に出ているのにクリックされていないクエリ。title/meta-descriptionの書き換えのみで改善する。";
$md[] = "";
$md[] = "| クエリ | 順位 | 表示 | CTR | 対象URL |";
$md[] = "|---|---|---|---|---|";
foreach (array_slice($titleFix, 0, 20, true) as $query => $q) {
    $md[] = sprintf("| %s | %.1f | %d | %.2f%% | %s |",
        $query, $q['pos'], $q['imp'], $q['ctr'] * 100, array_key_first($q['pages']));
}
$md[] = "";

$md[] = "## 4. 【優先度B】1ページ目を狙える強化候補（11〜30位）";
$md[] = "";
$md[] = "既にGoogleがテーマ性を認めているクエリ。対象ページへの内部リンク追加＋コンテンツ加筆（比較表・選び方）で押し上げる。";
$md[] = "";
$md[] = "| クエリ | 順位 | 表示 | 対象URL |";
$md[] = "|---|---|---|---|";
foreach (array_slice($boost, 0, 30, true) as $query => $q) {
    $md[] = sprintf("| %s | %.1f | %d | %s |",
        $query, $q['pos'], $q['imp'], array_key_first($q['pages']));
}
$md[] = "";

$md[] = "## 5. 【優先度C】ハブ記事の作成テーマ（頻出クラスタ）";
$md[] = "";
$md[] = "複数クエリに共通して表示が付いている語＝検索需要が実証済みのテーマ。「<語> おすすめ／比較／選び方」形式のハブ記事を作成し、該当商品ページへ内部リンクを張る。";
$md[] = "";
$md[] = "| テーマ語 | 関連クエリ数 | 合計表示 |";
$md[] = "|---|---|---|";
foreach (array_slice($hub, 0, 25, true) as $token => $t) {
    $md[] = sprintf("| %s | %d | %d |", $token, $t['queries'], $t['imp']);
}
$md[] = "";

$md[] = "## 6. 実行順";
$md[] = "";
$md[] = "1. **今週**: セクション3のtitle改修（上位20件）。テンプレ修正なら1日で完了";
$md[] = "2. **今週**: 表示ゼロのページタイプ（セクション2参照）の自動量産を停止／減速";
$md[] = "3. **来週〜**: セクション5の上位テーマからハブ記事を週2〜3本生成（Ollamaパイプライン転用）";
$md[] = "4. **継続**: セクション4の対象ページにハブ記事から内部リンク。月次で本レポートを再生成し順位変動を確認";
$md[] = "";

$out = OUT_DIR . '/kaizen_' . date('Ymd') . '.md';
file_put_contents($out, implode("\n", $md));
echo "完了: {$out}\n";
echo sprintf("タイトル改修候補: %d件 / 強化候補: %d件 / ハブテーマ: %d件\n",
    count($titleFix), count($boost), count($hub));
