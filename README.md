# Kurage Growth

Kurage Growth (`kgrowth`) is a weekly growth-analysis pipeline for AIxEC / AIxSNS / AIxTube.

It collects Google Search Console data and web access logs, analyzes search demand and real traffic, then generates a concrete improvement plan. The first target is to move from automated data registration to search-intent-driven content improvement.

## What It Does

- Fetches GSC Search Analytics data.
- Fetches simpletrack / web server `access.log` files by FTP.
- Parses access logs for traffic, bots, 404s, referrers, and page types.
- Combines GSC and access-log signals.
- Generates a weekly Markdown improvement plan in `reports/`.
- Generates machine-readable improvement job proposals in `data/improvement_jobs_latest.json`.

## Setup

```bash
cd /home/kojima/work/kgrowth
cp config.example.json config.json
```

Put the GSC service account JSON in `secrets/gsc-service-account.json`.

If Search Console does not accept a service account email, use Application
Default Credentials with your Google account instead:

```bash
gcloud auth application-default login --no-launch-browser \
  --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/cloud-platform
```

Then set this in `config.json`:

```json
{
  "gsc_auth": "gcloud"
}
```

Set FTP credentials with environment variables:

```bash
export KGROWTH_FTP_HOST='example.com'
export KGROWTH_FTP_USER='user'
export KGROWTH_FTP_PASS='password'
```

For the existing Exbridge/heteml environment, `config.example.json` points to
`web/aixec_exbridge_jp/access.log`. If environment variables are not set,
`ftp.legacy_helper` can read the existing local FTP helper file without
committing credentials to this repository.

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

This writes:

```text
data/analysis_latest.json
data/improvement_jobs_latest.json
reports/growth_plan_latest.md
```

Run the weekly pipeline:

```bash
python3 -m kgrowth.cli weekly --config config.json
```

## Weekly Loop

1. Collect GSC and access-log data.
2. Detect pages and query groups with search opportunity.
3. Generate a plan with concrete repo/file-level improvement candidates.
4. Generate improvement job proposals for kdeck Goal Queue.
5. Execute selected improvements in the owning repositories through rqdb4ai.
6. Compare next week's GSC/access-log data against the previous report.

## 24/365 Improvement Operation

Kurage Growth is not the worker runner. It is the analysis and job-proposal layer.

The intended always-on flow is:

```text
kgrowth weekly/analyze
  -> data/improvement_jobs_latest.json
  -> kdeck Goal Queue
  -> rqdb4ai generic execution queues
  -> app-owned jobs in AIxEC / AIxSNS / AIxTube / BuzBlogger
  -> simpletrack + GSC verification
```

The default strategy is Amazon-first because Amazon has confirmed sales while
Rakuten has higher click volume but no confirmed sales. Rakuten remains a
secondary path.

## Current Improvement Themes

- Rewrite BuzBlogger output around real search queries, not only buzz summaries.
- Add `noindex,follow` to duplicated register-log detail pages.
- Generate hub articles for query clusters that already have impressions.
- Use AIxTube videos outside the site where quality filters pass.

The samples in `samples/` are kept as the original PHP proof-of-concept for GSC fetching and reporting.
