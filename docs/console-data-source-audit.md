# Console game catalogue and price-source audit

Status: **source verification pending** (2026-10-20)

This document records the source gates for Nintendo Switch 2 and PlayStation 5 catalogue autocomplete and Taiwan price lookups. It intentionally does not claim that a source is approved merely because an endpoint is reachable.

## User requirements

- Nintendo Switch 2 physical and digital prices must be shown separately.
- Price region should represent what a Taiwan user can actually buy.
- /add and /lookup autocomplete should return matching game catalogue entries, not echo the raw query.
- No numeric price may be shown unless it is tied to a verified product/edition and a known region/currency.
- Keep all work on the PR feature branch; do not merge to main without approval.

## Existing repository facts

- The current Nintendo lookup link is the Nintendo Taiwan store landing page, not a product-specific price endpoint.
- Current console autocomplete returns a single choice containing the typed query. It is not a catalogue.
- Console watchlist rows use normalized title text as an identifier and are link-only. They do not identify a particular physical edition or digital SKU.
- The scheduled checker intentionally processes Steam only and must not be extended to consoles until a reliable provider is verified.
- Existing tests only assert link generation and link-only key normalization; they do not verify live catalogue or prices.

## Candidate-source gates

### Nintendo Taiwan official store — physical edition

Before implementation, verify against official documentation or direct, reproducible manual checks:

1. Whether a product search or product-detail endpoint is officially supported for public use.
2. Whether automated access is permitted by the site's terms/robots guidance.
3. Whether product details expose a stable product identifier, edition, stock status, and TWD price.
4. Whether the price shown is the actual Taiwan consumer price and how out-of-stock products are represented.

Until those checks pass, only provide an official store/search link and clearly label the numeric price as unavailable. Do not scrape product pages by default.

### Nintendo digital edition

The existence of a Nintendo Taiwan retail site does not establish that a Taiwan-region eShop with public digital prices exists. Confirm whether a Taiwan consumer-facing digital store is available and whether its prices can be queried through a supported, permitted interface.

If no such Taiwan-region source is confirmed, the digital-price field must say that a verified Taiwan digital price source is unavailable. Do not silently substitute Japan/US eShop prices, exchange-rate conversions, or physical-card prices.

### Third-party game catalogues

A catalogue provider is acceptable only after verifying:

- official API documentation and authentication requirements;
- terms/licence covering this bot's intended use, attribution, storage/caching and rate limits;
- supported platform metadata (specifically Nintendo Switch 2, not merely Nintendo Switch);
- stable IDs and useful search results for Traditional Chinese and English names;
- graceful handling of timeout, rate limit, empty results, malformed payload and provider outage.

A valid catalogue result is not evidence of a valid price. Catalogue and price providers must remain independent.

### Retailer price comparison for physical games

A third-party retailer source must expose the exact product/edition and TWD price, identify the retailer, and permit automated access. Search-engine result snippets and generic search links are not a price feed and must not be presented as verified prices.

## Implementation acceptance criteria

1. Search results are real catalogue records; autocomplete returns at most Discord's 25 choices and each choice value maps to a stable source ID.
2. A query with no matches returns no choices; provider errors fail closed without echoing the query as if it were a match.
3. Physical and digital prices are separate fields/sections, each with source, currency, product/edition, and retrieval timestamp.
4. Missing source data is rendered as “目前無可驗證價格資料”, never as zero or a guessed value.
5. A digital price is never inferred from a physical listing; prices from different regions are never silently combined.
6. Unit tests mock network responses; they cover matching, ID mapping, duplicate titles, version disambiguation, timeouts, HTTP errors, malformed JSON, missing prices, and Discord's 25-choice cap.
7. Tests do not rely on live third-party services. A separate manual smoke test may verify source availability before release.
8. CI passes on the PR head and the PR remains Draft until the source gates and live smoke test are complete.

## Current decision

**No third-party catalogue or numeric console-price provider is approved yet.** The available repository tools can inspect and modify GitHub repository resources, but do not provide a general web browser for independently validating non-GitHub vendor terms and live endpoints. Therefore the implementation must not claim source verification is complete. Next step is to review official source documentation/terms and record the exact URLs and allowed use here, then implement only against the approved provider(s).
