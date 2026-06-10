# Kurage Growth

Kurage Growth (`kgrowth`) is a weekly growth-analysis pipeline for AIxEC / AIxSNS / AIxTube.

It collects Google Search Console data and web access logs, analyzes search demand and real traffic, then generates a concrete improvement plan. The first target is to move from automated data registration to search-intent-driven content improvement.

## What It Does

- Fetches GSC Search Analytics data.
- Fetches simpletrack / web server `access.log` files by FTP.
- Parses access logs for traffic, bots, 404s, referrers, and page types.
- Combines GSC and access-log signals.
- Generates a weekly Markdown improvement plan in `reports/`.

## Setup

```bash
cd /home/kojima/work/kgrowth
cp config.example.json config.json
```

Put the GSC service account JSON in `secrets/gsc-service-account.json`.

Set FTP credentials with environment variables:

```bash
export KGROWTH_FTP_HOST='example.com'
export KGROWTH_FTP_USER='user'
export KGROWTH_FTP_PASS='password'
```

Do not commit `config.json`, `secrets/`, downloaded logs, or generated reports containing private data.

## Commands

Fetch GSC:

```bash
python3 -m kgrowth.cli fetch-gsc --config config.json
```

Fetch access logs:

```bash
python3 -m kgrowth.cli fetch-logs --config config.json
```

Analyze current data:

```bash
python3 -m kgrowth.cli analyze --config config.json
```

Run the weekly pipeline:

```bash
python3 -m kgrowth.cli weekly --config config.json
```

## Weekly Loop

1. Collect GSC and access-log data.
2. Detect pages and query groups with search opportunity.
3. Generate a plan with concrete repo/file-level improvement candidates.
4. Execute selected improvements in the owning repositories.
5. Compare next week's GSC/access-log data against the previous report.

## Current Improvement Themes

- Rewrite BuzBlogger output around real search queries, not only buzz summaries.
- Add `noindex,follow` to duplicated register-log detail pages.
- Generate hub articles for query clusters that already have impressions.
- Use AIxTube videos outside the site where quality filters pass.

The samples in `samples/` are kept as the original PHP proof-of-concept for GSC fetching and reporting.
