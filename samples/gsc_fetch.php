<?php
/**
 * gsc_fetch.php — Google Search Console データ取得
 *
 * Search Analytics API から クエリ×ページ の実績を取得し JSON 保存する。
 * 依存なし（composer不要）。サービスアカウントJSONキーのみ必要。
 *
 * 事前準備:
 *   1. GCPコンソールでプロジェクト作成 → 「Google Search Console API」を有効化
 *   2. サービスアカウント作成 → JSONキーをダウンロード → 下記 KEY_FILE に配置
 *   3. Search Console のプロパティ設定 → ユーザー追加 →
 *      サービスアカウントのメールアドレス（xxx@xxx.iam.gserviceaccount.com）を「閲覧者」で追加
 *
 * 実行: php gsc_fetch.php
 * 出力: data/gsc_latest.json
 */

// ===== 設定 =====
const KEY_FILE   = __DIR__ . '/service-account.json';
// URLプレフィックスプロパティなら 'https://aixec.exbridge.jp/'
// ドメインプロパティなら 'sc-domain:exbridge.jp'
const SITE_URL   = 'https://aixec.exbridge.jp/';
const DAYS_BACK  = 28;       // 取得期間（日数）
const OUT_DIR    = __DIR__ . '/data';
const ROW_LIMIT  = 25000;    // APIの1リクエスト上限
// ================

function get_access_token(string $keyFile): string {
    $key = json_decode(file_get_contents($keyFile), true);
    if (!$key) die("ERROR: キーファイルが読めません: {$keyFile}\n");

    $now = time();
    $header = ['alg' => 'RS256', 'typ' => 'JWT'];
    $claim = [
        'iss'   => $key['client_email'],
        'scope' => 'https://www.googleapis.com/auth/webmasters.readonly',
        'aud'   => 'https://oauth2.googleapis.com/token',
        'iat'   => $now,
        'exp'   => $now + 3600,
    ];
    $b64 = fn($d) => rtrim(strtr(base64_encode(json_encode($d)), '+/', '-_'), '=');
    $input = $b64($header) . '.' . $b64($claim);

    openssl_sign($input, $sig, $key['private_key'], 'sha256WithRSAEncryption');
    $jwt = $input . '.' . rtrim(strtr(base64_encode($sig), '+/', '-_'), '=');

    $ch = curl_init('https://oauth2.googleapis.com/token');
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'grant_type' => 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion'  => $jwt,
        ]),
        CURLOPT_RETURNTRANSFER => true,
    ]);
    $res = json_decode(curl_exec($ch), true);
    curl_close($ch);

    if (empty($res['access_token'])) {
        die("ERROR: トークン取得失敗: " . json_encode($res, JSON_UNESCAPED_UNICODE) . "\n");
    }
    return $res['access_token'];
}

function query_search_analytics(string $token, array $body): array {
    $url = 'https://www.googleapis.com/webmasters/v3/sites/'
         . rawurlencode(SITE_URL) . '/searchAnalytics/query';
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Content-Type: application/json',
        ],
        CURLOPT_POSTFIELDS => json_encode($body),
        CURLOPT_RETURNTRANSFER => true,
    ]);
    $raw = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $res = json_decode($raw, true);
    if ($code !== 200) {
        die("ERROR: API応答 {$code}: " . substr($raw, 0, 500) . "\n");
    }
    return $res['rows'] ?? [];
}

function fetch_all(string $token, array $dimensions, string $start, string $end): array {
    $all = [];
    $startRow = 0;
    do {
        $rows = query_search_analytics($token, [
            'startDate'  => $start,
            'endDate'    => $end,
            'dimensions' => $dimensions,
            'rowLimit'   => ROW_LIMIT,
            'startRow'   => $startRow,
        ]);
        $all = array_merge($all, $rows);
        $startRow += ROW_LIMIT;
        echo "  " . count($all) . " 行取得...\n";
    } while (count($rows) === ROW_LIMIT);
    return $all;
}

// ===== メイン =====
$end   = date('Y-m-d', strtotime('-2 days'));  // GSCデータは2日遅れ
$start = date('Y-m-d', strtotime("-" . (DAYS_BACK + 2) . " days"));

echo "対象: " . SITE_URL . "\n期間: {$start} 〜 {$end}\n";
echo "認証中...\n";
$token = get_access_token(KEY_FILE);

echo "[1/3] クエリ×ページ を取得\n";
$queryPage = fetch_all($token, ['query', 'page'], $start, $end);

echo "[2/3] ページ別集計 を取得\n";
$pages = fetch_all($token, ['page'], $start, $end);

echo "[3/3] 日別推移 を取得\n";
$dates = fetch_all($token, ['date'], $start, $end);

if (!is_dir(OUT_DIR)) mkdir(OUT_DIR, 0755, true);
$out = [
    'site'       => SITE_URL,
    'start'      => $start,
    'end'        => $end,
    'fetched_at' => date('c'),
    'query_page' => $queryPage,
    'pages'      => $pages,
    'dates'      => $dates,
];
$file = OUT_DIR . '/gsc_latest.json';
file_put_contents($file, json_encode($out, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
// 履歴も保持
copy($file, OUT_DIR . '/gsc_' . date('Ymd') . '.json');

echo "完了: {$file}\n";
echo "クエリ×ページ: " . count($queryPage) . "行 / ページ: " . count($pages) . "行\n";
echo "次に php gsc_report.php を実行してください。\n";
