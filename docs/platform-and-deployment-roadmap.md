# Platform and deployment roadmap

Status: design requirements; not all capabilities are implemented.

## Delivery approach

**Develop and test locally first; deploy to the cloud only after the feature set is complete and validated.** Do not start a cloud migration, add hosting costs, or introduce deployment complexity just to continue feature development.

The later goal is for the Discord bot and scheduled checks to keep working when the user's personal computer is turned off. Build portability and persistence boundaries now, but keep local development and testing as the active workflow until the user decides the feature set is ready.

## Product scope

- Automated interactive lookup currently covers Steam, Nintendo Switch (NS), and Nintendo Switch 2 (NS2).
- PS5 automated search and lookup are out of scope. Existing manually maintained PS5 watchlist rows may remain visible and removable, but must not be treated as verified price products or automatically queried.
- Scheduled discount notifications are Steam-only. Other platforms are skipped unless a provider and notification policy are explicitly implemented and tested.
- NS and NS2 are separate platform targets. A title may have an NS release, a native NS2 release, an NS2 Edition, or an upgrade path. Title matching alone must never merge these products.
- Keep digital storefront prices separate from physical retailer prices. Store region, currency, source, edition/product ID, and retrieval timestamp with every numeric offer.
- The product focuses on current-price lookup and discount notifications. Historical price collection, historical-price commands, and price-trend charts are out of scope.
- Never present an unverified source or inferred price as a directly observed current price.

## Architecture constraints

### Platform-neutral product identity

Keep platform and provider IDs namespaced; do not assume one global ID or that one title equals one purchasable product. The data model may remain extensible for future platforms without exposing automated lookup for a platform that is currently out of scope.

A current offer should be traceable to at least:
- platform and exact release/edition;
- store or retailer and digital/physical channel;
- product identifier from the source;
- region and source-reported currency;
- current price and discount/availability status where provided;
- source/provider URL and retrieval timestamp;
- any data-quality caveat or verification status.

NS, NS2, and NS2 Edition should not automatically be treated as equivalent. Record upgrade relationships only when a source confirms them. Missing platform metadata must remain explicitly unverified.

### Provider adapters

Keep catalogue search and current-price retrieval separate: a catalogue result identifies a candidate product; a price adapter retrieves an offer for that product. Keep provider-specific HTTP parsing outside Discord command handlers and notification orchestration.

Provider outages, missing IDs, rate limits, malformed responses, missing currency, and uncertain regional availability must fail closed rather than fabricate a price or silently switch regions. Provider adapters should have mocked tests and a documented source/licensing/rate-limit review before production use.

Nintendo's current candidate endpoints are undocumented and automated reuse permission is unconfirmed. The code path is experimental, not source approval. Do not enable scheduled Nintendo price notifications from this adapter. Physical NS/NS2 prices need a separately reviewed retailer source.

### Local development now

- Keep feature development, manual smoke tests, and regression tests runnable on the developer's computer.
- Load secrets from local environment/configuration for local runs; never commit tokens or webhook URLs.
- Avoid hard-coded machine-specific absolute paths or treating a local cache as authoritative production data.
- Keep persistence behind a small boundary where practical, so local storage can later be replaced by durable cloud-capable storage without rewriting commands and provider logic.
- Keep tests deterministic with mocked network/provider responses. Live endpoint checks are explicit manual tests, not a requirement for the normal test suite.
- Document required local cache setup and fail clearly when a required cache is missing or stale.

### Cloud deployment later

- Do not migrate hosting before the user decides the feature set is ready.
- At deployment time, choose a managed scheduler/worker or suitable host so scheduled checks and any required persistent Discord connection can run while the personal computer is off.
- Treat GitHub Actions runners as ephemeral; files written only to a runner are not reliable long-term storage.
- Store watchlists and notification/deduplication state in a durable shared store or version-controlled persistence layer with concurrency protection. If repository JSON remains the interim store, document its limits and preserve conflict handling.
- Keep secrets in the deployment platform's secret manager/repository secrets; never commit tokens or webhook URLs.
- Make scheduled runs idempotent and safe to retry. Persist notification state so a retry is unlikely to send duplicate alerts; document the unavoidable boundary between sending an external message and persisting local state.
- Add timeouts, bounded retries/backoff for transient failures, provider-level rate limits, structured logs, and failure alerts/health checks.
- Make timezone and schedule explicit. The current GitHub Actions schedule is 12:06 UTC (20:06 Taiwan time); confirm the desired cadence before changing it.
- Validate cloud operation with the developer's computer off, monitor failures, test recovery from interrupted runs, and verify duplicate-notification behaviour.

## Suggested staged delivery

1. **Now — local reliability:** complete Discord commands, watchlist mutation, Steam current-price lookup, and Steam discount notifications. Keep regression tests runnable locally.
2. **Provider boundaries:** keep search, catalogue matching, price normalization, and persistence separate from Discord handlers. Add tests for duplicate titles, editions, regions, currency, missing IDs, and physical-versus-digital offers.
3. **Source approval:** review official documentation/terms, attribution, rate limits, caching, and permitted use before relying on each provider. Keep Nintendo numeric lookup clearly experimental until that review is complete.
4. **Pre-deployment hardening:** test persistence boundaries, retries, state migration/export, notification deduplication, secrets configuration, and fresh-process startup.
5. **When features are ready — cloud migration:** select hosting and durable storage, deploy, verify schedules and alerts with the personal computer off, and keep a rollback path.

## Acceptance criteria

- Steam, NS, and NS2 products can be selected independently where supported by the current lookup flow; PS5 is not exposed as an automated lookup platform.
- NS, NS2, and NS2 Edition offers are not conflated; physical and digital prices are distinct.
- Every displayed numeric price has an explicit source product, edition/platform verification status, region, source-reported currency, and retrieval time where the provider exposes it.
- The bot supports current-price lookup and discount notifications; historical-price collection and query features are not required.
- Scheduled price checks query Steam only and skip non-Steam rows without treating them as Steam IDs.
- Normal development and regression tests run locally before cloud migration and do not depend on live third-party services.
- A later cloud deployment can run scheduled collection and send Discord alerts without the user's computer being on.
- A cold start can load durable state and complete safely.
- Retried or overlapping scheduled jobs do not corrupt watchlists; notification idempotency limitations are documented and tested.
- Unsupported or unverified prices remain explicitly unavailable rather than guessed.
