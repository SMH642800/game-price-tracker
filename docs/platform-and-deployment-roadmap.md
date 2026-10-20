# Platform and cloud deployment roadmap

Status: design requirements; not all capabilities are implemented.

## Product requirements

- Support Steam, PlayStation 5 (PS5), Nintendo Switch (NS), and Nintendo Switch 2 (NS2).
- Treat NS and NS2 as distinct platform targets. A title may have an NS release, an NS2 release, an NS2 Edition, an upgrade path, or only some of these. Keep product/edition identity explicit; title matching alone must never merge records.
- Keep digital storefront prices separate from physical retailer prices. Store region, currency, source, edition/product ID, observation time, and availability status with every price.
- Preserve the existing rule that unverified sources, inferred prices, and third-party historical estimates must not be presented as directly observed bot prices.
- Run scheduled checks and send notifications without requiring a user's Mac or other personal computer to be powered on.

## Architecture constraints

### Platform-neutral domain model

Use shared concepts for games, platform releases/editions, store offers, price observations, watchlist entries, and notification rules. Provider-specific IDs must be namespaced by provider/platform/region; do not assume one global ID or one title equals one purchasable product.

A price observation should be traceable to at least:
- platform and edition/release;
- store or retailer and digital/physical channel;
- product identifier from the source;
- region and currency;
- regular/current price and discount status where available;
- source URL/provider and retrieval timestamp;
- availability/status and any data-quality caveat.

NS2 Edition should not automatically be treated as equivalent to a native NS2 release or the NS version. Explicitly represent upgrade eligibility/relationships only when a source confirms them.

### Provider adapters

Keep catalogue search and price retrieval separate: a catalogue result identifies the exact product; a price adapter retrieves offers for that product. Provider outages, missing IDs, rate limits, malformed responses, and uncertain regional availability must fail closed rather than fabricate a price or silently switch regions.

Use a provider interface so platform-specific source changes do not spread into Discord commands or persistence logic. Every provider must have mocked tests and documented source/licensing/rate-limit review before production use. Nintendo's currently probed endpoints remain undocumented and unapproved; do not treat the probe as permission for scheduled reuse. Physical NS/NS2 prices need a separately approved retailer source.

### Cloud-first operation

- Treat GitHub Actions as the current scheduler, not as durable storage. Workflow runners are ephemeral; files written only to the runner are not a reliable long-term database.
- Store watchlists, price observations, and notification/deduplication state in a durable shared store or a version-controlled persistence layer with concurrency protection. If repository JSON remains the interim store, document its limits and preserve conflict retries; avoid relying on local disk caches for production state.
- Keep secrets in the deployment platform's secret manager/repository secrets; never commit tokens or webhook URLs.
- Make scheduled runs idempotent and safe to retry. Persist successful observations and notification state so a retry does not lose history or send duplicate alerts.
- Add timeouts, bounded retries/backoff for transient failures, provider-level rate limits, structured logs, and failure alerts/health checks.
- Make timezone and schedule explicit. The current GitHub Actions schedule is 12:06 UTC (20:06 Taiwan time); confirm desired cadence before changing it.
- Keep Discord commands and the scheduled price checker deployable without a developer machine. Avoid dependencies on local absolute paths, local-only files, or a process that must stay running on a home computer.

## Suggested staged delivery

1. **Now — harden the current workflow:** maintain platform-neutral IDs and source boundaries; test state persistence, concurrent writes, retries, and notification idempotency. Keep unsupported console prices link-only.
2. **Next — catalogue and offer contracts:** define provider interfaces and normalized models; add NS and NS2 as distinct platform values; test duplicate titles, editions, upgrades, regions, and physical-vs-digital offers.
3. **Then — source approval and integration:** approve a source for each platform/channel before enabling numeric pricing. Keep each source's terms, API documentation, rate limits, attribution, and live smoke-test results in the source audit.
4. **Cloud persistence:** when file-based repository state becomes fragile or concurrency needs grow, migrate to a managed database or another durable store. Preserve export/backup and migration tests.
5. **Cloud operations:** validate scheduled execution with the developer's computer off, monitor failures, test recovery from interrupted runs, and verify no duplicate notifications.

## Acceptance criteria

- A single title can be tracked independently on Steam, PS5, NS, and NS2 where matching releases exist.
- NS, NS2, and NS2 Edition offers are not conflated; physical and digital prices are distinct.
- Every numeric price is linked to a specific source product, edition, region, currency, and observation time.
- No local computer is required for scheduled collection, history retention, or Discord alerts.
- A cold start on a fresh runner can load durable state and complete safely.
- Retried or overlapping scheduled jobs do not corrupt history or send duplicate notifications.
- CI uses mocked provider responses and does not depend on live third-party services.
- Unsupported or unverified prices remain explicitly unavailable rather than guessed.
