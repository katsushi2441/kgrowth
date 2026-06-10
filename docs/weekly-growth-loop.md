# Weekly Growth Loop

Kurage Growth is the analysis layer for improving AIxEC / AIxSNS / AIxTube search performance.

## Inputs

- Google Search Console Search Analytics data.
- simpletrack / web server `access.log`.
- Existing site structure and generated content patterns.

## Outputs

- `reports/growth_plan_YYYYMMDD.md`
- `reports/growth_plan_latest.md`
- `data/analysis_latest.json`

## Decision Rules

- GSC has priority for search intent.
- access.log has priority for real traffic, broken pages, bots, and referral behavior.
- Product registration volume is not treated as success by itself.
- The weekly report must point to concrete improvements that can be executed in the owning repositories.

## Execution Phases

1. **Observe**
   - Fetch GSC.
   - Fetch access logs.
   - Parse current traffic and search status.

2. **Diagnose**
   - Find low CTR pages already ranking.
   - Find 11〜30位 queries that can be pushed upward.
   - Find query clusters suitable for hub articles.
   - Find broken URLs, low-quality generated pages, and bot-heavy patterns.

3. **Plan**
   - Write a Markdown improvement plan.
   - Include priority, target area, and verification commands.

4. **Act**
   - Implement selected changes in the owning repositories.
   - Keep app-specific logic outside `kgrowth` unless it is only analysis metadata.

5. **Compare**
   - Next week, compare impressions, CTR, ranking movement, access-log traffic, and 404s.

## Current Priority Themes

- BuzBlogger should answer real search queries.
- Register-log SNS posts should not become indexable duplicate pages.
- Hub articles should be generated from proven GSC clusters.
- AIxTube videos should be distributed only after quality filtering.
