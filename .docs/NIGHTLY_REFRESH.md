# Nightly refresh of the demo corpus

Configured and verified November 8, 2026 (America/Vancouver).

The live workflow is enabled at **23:00 America/Vancouver every night**:

1. Refresh the repository IDs in the current active snapshot, including published
   security advisories. Do not discover additional repositories.
2. Fully refresh the bronze, silver and gold pipeline. The scraper replaces stable
   filenames, so incremental ingestion alone would not reliably read the new data.
3. Run the existing AI maintenance investigator with its default budget of 10
   priority repositories, then the existing summary task.

Each task requires the preceding task to succeed. Existing-only scraping requires
every saved repository to refresh successfully before publishing; unavailable
repositories cause the scrape to fail and retain the previous active snapshot.
Security scans remain on demand.

## Deployment

- [Nightly workflow](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/1090806187868503)
- [Scraper job](https://dbc-a0a04386-0e40.cloud.databricks.com/jobs/185379822037489)
- Updated the existing scraper notebook and these two jobs only. A full bundle
  deployment was not used because the unrelated Apps resource references an
  unstaged `apps/corpus-explorer` directory.
- Verified the live cron, timezone, enabled status, existing-only parameter,
  dependency order, full-refresh flag, and retained 10-repository investigation
  budget. Exported notebook content matches the local tested source.
- Neither job had an active run during the update. No scrape was triggered as
  part of deployment; the first complete nightly execution remains unverified.

The checked-in bundle resources describe the same configuration for future deployments.
Standalone scraper runs still default to discovery; pass `repo_source=existing`
to refresh the active corpus explicitly.

## Validation

All 27 scraper tests passed, including existing-only selection without discovery,
retaining the previous snapshot when a repository cannot refresh, and stopping
on an invalid saved snapshot. `git diff --check` passed.

A broader test discovery run encountered unrelated missing dependencies and
tracing-test errors (`ensure_alternatives` undefined); it did not pass. Full
bundle validation is also blocked by the missing staged Apps directory above.
The targeted job updates were accepted by Databricks and verified by reading
their deployed settings back.
