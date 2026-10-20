# Platform and deployment roadmap

Status: design requirements; not all capabilities are implemented.

## Delivery approach

**Develop and test locally first; deploy to the cloud only after the feature set is complete and validated.** The current workflow should remain convenient for local development. Do not start a cloud migration, add hosting costs, or introduce deployment complexity just to continue feature development.

Cloud deployment is a later release stage: the goal is for the Discord bot and scheduled price checks to keep working when the user's personal computer is turned off. Build portability and persistence boundaries now so this later move is straightforward, but keep using local execution for development and tests until the user is ready to deploy.

## Product requirements

- Support Steam, PlayStation 5 (PS5), Nintendo Switch (NS), and Nintendo Switch 2 (NS2).
- Treat NS and NS2 as distinct platform targets. A title may have an NS release, an NS2 release, an NS2 Edition, an upgrade path, or only some of these. Keep product/edition identity explicit; title matching alone must never merge records.
- Keep digital storefront prices separate from physical retailer prices. Store region, currency, source, edition/product ID, observation time, and availability status with every price.
- Preserve the existing rule that unverified sources, inferred prices, and third-party historical estimates must not be presented as directly observed bot prices.
- Final cloud operation must not require a user's Mac or other personal computer to be powered on.

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

### Local development now

- Keep feature development, manual smoke tests, and regression tests runnable on the developer's computer.
- Load secrets from local environment/configuration for local runs; never commit tokens or webhook URLs.
- Avoid hard-coded local absolute paths, implicit dependence on a particular machine, or treating local cache files as authoritative production data.
- Keep persistence behind a small interface where practical, so local development storage can later be replaced by a durable cloud-capable backend without rewriting commands and price-provider logic.
- Keep tests deterministic with mocked network/provider responses. Live endpoint checks should remain explicit manual tests, not a requirement for the normal test suite.

### Cloud deployment later

- Do not migrate hosting before the user decides the feature set is ready. Cloud deployment is a planned release step, not a prerequisite for current development.
- At deployment time, choose a managed scheduler/worker or other suitable hosting so scheduled checks and any required persistent Discord connection can run while the personal computer is off.
- Treat GitHub Actions runners as ephemeral; files written only to a runner are not reliable long-term storage.
- Store watchlists, price observations, and notification/deduplication state in a durable shared store or a version-controlled persistence layer with concurrency protection. If repository JSON remains the interim store, document its limits and preserve conflict retries.
- Keep secrets in the deployment platform's secret manager/repository secrets; never commit tokens or webhook URLs.
- Make scheduled runs idempotent and safe to retry. Persist successful observations and notification state so a retry does not lose history or send duplicate alerts.
- Add timeouts, bounded retries/backoff for transient failures, provider-level rate limits, structured logs, and failure alerts/health checks.
- Make timezone and schedule explicit. The current GitHub Actions schedule is 12:06 UTC (20:06 Taiwan time); confirm desired cadence before changing it.
- Validate cloud operation with the developer's computer off, monitor failures, test recovery from interrupted runs, and verify no duplicate notifications.

## Suggested staged delivery

1. **Now — finish local development:** implement and test Discord commands, watchlists, source adapters, price history, and notification behaviour locally. Keep unsupported console prices link-only.
2. **Next — catalogue and offer contracts:** define provider interfaces and normalized models; add NS and NS2 as distinct platform values; test duplicate titles, editions, upgrades, regions, and physical-vs-digital offers.
3. **Then — source approval and integration:** approve a source for each platform/channel before enabling numeric pricing. Keep each source's terms, API documentation, rate limits, attribution, and live smoke-test results in the source audit.
4. **Pre-deployment hardening:** test persistence boundaries, retries, state migration/export, notification idempotency, secrets configuration, and fresh-process startup.
5. **When features are ready — cloud migration:** select hosting and durable storage, deploy, verify schedules and alerts with the personal computer off, and keep a rollback path.

## Acceptance criteria

- A single title can be tracked independently on Steam, PS5, NS, and NS2 where matching releases exist.
- NS, NS2, and NS2 Edition offers are not conflated; physical and digital prices are distinct.
- Every numeric price is linked to a specific source product, edition, region, currency, and observation time.
- Normal development and regression tests continue to run locally before cloud migration.
- The later cloud deployment can run scheduled collection, retain history, and send Discord alerts without the user's computer being on.
- A cold start on a fresh deployment can load durable state and complete safely.
- Retried or overlapping scheduled jobs do not corrupt history or send duplicate notifications.
- CI uses mocked provider responses and does not depend on live third-party services.
- Unsupported or unverified prices remain explicitly unavailable rather than guessed.
