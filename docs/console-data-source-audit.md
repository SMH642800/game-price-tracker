# Nintendo game catalogue and price-source audit

Status: **source verification pending** (2026-10-20)

This document records the source gates for Nintendo Switch and Nintendo Switch 2 catalogue autocomplete and Taiwan digital-price lookups. PS5 automated lookup is out of scope for the current bot; any manually maintained PS5 watchlist row is reference-only. It intentionally does not claim that a source is approved merely because an endpoint is reachable.

## User requirements

- Nintendo Switch 2 physical and digital prices must be shown separately.
- Price region should represent what a Taiwan user can actually buy.
- /add and /lookup autocomplete for NS and NS2 should return matching game catalogue entries, not echo the raw query.
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


## Additional source leads (reviewed 2026-10-20)

### Nintendo price endpoint lead

A public GitHub project, [Switch-eShopRadar](https://github.com/YuHaoLiaoSideProject/Switch-eShopRadar), documents a community smoke test of:

- `https://api.ec.nintendo.com/v1/price?country=TW&lang=zh&ids=...`
- It reports `lang=zh` or `lang=en` is required (`zh-TW` reportedly returns HTTP 400), a batch limit of 50 IDs, and fields including `sales_status`, `regular_price`, and sometimes `discount_price`.
- Its own decision record explicitly classifies Nintendo price/catalog endpoints as **undocumented/non-official interfaces subject to change**, despite being hosted on a Nintendo domain.

This is useful evidence that a Taiwan price endpoint may work, but it is **not Nintendo API documentation or permission to automate it**. Before enabling it in production, verify with a live request against known NSUIDs (including a discounted title, a non-discounted title, an unavailable title, and a Switch 2-specific title), record actual response shapes, and review Nintendo's applicable terms/robots guidance. The endpoint alone cannot identify games; a catalogue that maps a title to the correct NSUID is still required. Do not reuse third-party Algolia application credentials or assume their quota/terms permit this bot.

Reference reviewed: [Switch-eShopRadar technical decision record](https://github.com/YuHaoLiaoSideProject/Switch-eShopRadar/blob/7eb7fe9a5b2a98f81cad65d1aad2dc5dd1fd3ba0/docs/tech-decision-Switch-eShopRadar-2026-08-23.md).

### eShop-Prices

User supplied an example game page at [eShop-Prices](https://eshop-prices.com/games/21892-the-legend-of-zelda-ocarina-of-time). The site appears useful as a possible source of English-titled, multi-region digital-price comparisons, but a game page is not an API contract. We have not verified whether the site provides a supported public API, its terms for automated access/reuse, rate limits, caching rules, or whether its displayed values can be consumed without scraping. **Do not scrape pages or import its data until those checks are completed.** If no permitted API is documented, use the site as a human-facing link only.

### Catalogue/autocomplete direction

- The Nintendo price endpoint is a price lookup by product/NSUID, not a title-search catalogue.
- The cited Switch-eShopRadar record says the official Taiwan software listing is only a partial seed and its US Algolia index is a third-party/unofficial discovery source. The record is useful as a lead, not a licence grant or independent proof of current availability.
- A catalogue candidate must identify Nintendo Switch 2 specifically and return a stable product ID. Search results must not be matched to price records by title text alone.
- For Taiwan-first digital lookup, query the Taiwan price source only after a catalogue result supplies a verified regional product ID. If the product is not available in Taiwan, the fallback should be an explicitly labelled Japan-region lookup using a Japanese-region product ID and JPY currency. Do not infer Taiwan unavailability from a generic HTTP error or silently convert JPY to TWD.
- Physical pricing remains a separate provider and data model. The Nintendo digital-price endpoint must never be treated as a physical retailer price feed.

### Current verification status

The available tools in this work session can inspect public GitHub content but cannot directly run reproducible requests against Nintendo or eShop-Prices, nor inspect those sites' current legal/robots pages. Accordingly, the Nintendo endpoint is a **promising but unapproved technical lead**; eShop-Prices is a **human-reference lead only**. Numeric Nintendo prices and catalogue-backed autocomplete remain gated until a live smoke test and permitted-use review are documented.

## Adapter implementation progress (2026-10-20)

A first isolated adapter has been added at `nintendo.py`, with mocked unit tests in `tests/test_nintendo.py`. It:
- validates numeric title IDs and only allows TW/JP regions;
- requests the candidate endpoint with `country`, `lang`, and `ids`;
- matches the response by exact `title_id` (never by title text);
- separates regular, discount, and current price; preserves region/currency/status/source timestamp;
- distinguishes an explicit non-sale status from an absent record and never silently retries another region;
- fails closed on HTTP errors, invalid JSON, and unexpected schema.

This is a **tested-by-design adapter scaffold, not yet a production-enabled integration**. The source remains undocumented and no live API smoke test or terms review has been completed in this environment. The current Discord command still does not call this adapter.

### Remaining release blockers

1. **Catalogue/autocomplete:** no approved, sufficiently broad Nintendo Switch 2 title-search source has been verified. The price endpoint cannot search titles. Do not reuse third-party Algolia credentials. eShop-Prices remains a human-facing reference until its API and reuse terms are confirmed.
2. **Taiwan-to-Japan fallback:** only implement automatic fallback after the API's regional availability signals are live-tested and shown to distinguish "not sold in Taiwan" from missing ID, API outage, or schema change.
3. **Physical edition price:** no permitted, verified retailer price feed is selected. Until then, the UI must explicitly say physical price is unavailable and link to a search; never reuse digital price.
4. **Discord integration:** once the catalogue is approved, autocomplete choice values should be stable title IDs; the display label must include enough title/platform/edition detail to distinguish duplicate editions. Then wire `/lookup` and `/add` to the chosen result and the price adapter.
5. **Validation:** run `python -m unittest discover -s tests -v` and confirm PR CI on the updated head; separately perform a documented manual live smoke test for Taiwan, Japan, sale, non-sale, missing record, and Switch 2 title IDs.

Until blockers 1–3 are resolved, console numeric prices remain disabled and this PR must remain Draft.


## Additional Nintendo Taiwan catalogue probe (2026-10-20)

A second public repository, [samsonjaw/tw-switch-price](https://github.com/samsonjaw/tw-switch-price), documents the candidate Nintendo Taiwan catalogue endpoint:

- Catalogue: `https://www.nintendo.com/tw/api/software?sftab=all&spage=1`
- Price: `https://api.ec.nintendo.com/v1/price?country=TW&lang=zh&ids=...`

Its validation script reports a catalogue response shape with `items`, `total`, `title`, and `nsuid`, and a price response with `prices`, `title_id`, `sales_status`, `regular_price`, and optional `discount_price`. This is a useful implementation lead, but it remains community evidence: neither endpoint is documented as a stable public API contract, and the referenced repository does not expose a LICENSE file in the inspected root. We therefore do not copy its code or treat its existence as permission to reuse its dataset.

A low-rate, manual-only diagnostic was added at `scripts/probe_nintendo_sources.py`. On a cache miss it reads the catalogue sequentially (200 ms between page requests), searches the user's test terms (`時之笛`, `亰都幻都`, `京都幻都`, `Kyoto Xanadu`), and requests prices only for matching NSUIDs. To reduce repeat-run latency, it now caches the catalogue locally for 24 hours at `.cache/nintendo_tw_catalogue.json` (ignored by Git); `--refresh-cache` bypasses the cache and `--no-cache` disables it. Output includes cache status, unique/duplicate NSUID counts, and elapsed-time diagnostics. It remains a manual diagnostic, does not run in CI, and does not enable production commands.

### Required interpretation of probe output

- A matching catalogue row with an NSUID plus a matching `title_id` price record is evidence that the endpoint works for that item at that moment, not evidence of permission for production automation.
- A missing Taiwan match or price record does **not** prove that the game is not sold in Taiwan. It may mean the catalogue is incomplete, an NSUID is missing, a title is named differently, or the endpoint response changed.
- Automatic Japan fallback must wait until a Japan catalogue/search source can identify the corresponding Japanese product ID and live tests can distinguish regional unavailability from missing IDs, network errors, and schema changes.
- The probe does not identify physical retail editions or retailer prices. Physical prices remain unavailable until a separate permitted retailer source is selected.
- The user-supplied test cases must be evaluated from live output: *時之笛* should be non-discounted if a valid Taiwan price record exists; *亰都幻都-櫻花幻舞-* should show a discount only if Nintendo's returned `discount_price` and sales status actually indicate an active sale. Do not assume either status from the game title alone.


## Experimental Discord lookup integration (2026-10-20)

At the user's request, the Draft PR now wires the Nintendo Taiwan catalogue cache and candidate digital-price endpoint into `/lookup` for NS and NS2. This is an **experimental lookup path**, not a declaration that the source has been approved for stable production use.

- The catalogue cache is generated by the manual probe at `.cache/nintendo_tw_catalogue.json`; it expires after 24 hours. The Discord autocomplete reads the cache only and fails closed when it is missing or stale, avoiding a multi-minute catalogue crawl during Discord's autocomplete timeout window.
- Autocomplete choices map to exact numeric NSUIDs. Where the catalogue has an explicit platform field, NS and NS2 are filtered separately. Some real catalogue rows have `platform: null` (the probe found this for 時之笛), so these remain searchable but are visibly marked as platform-unverified; the bot does not claim that missing metadata proves a generation. Lookup never matches a price by title text alone.
- Price lookup queries Taiwan (TW / zh) only. It does not fall back to Japan, convert currencies, or substitute physical retailer prices.
- Responses identify the Nintendo result as a digital price and disclose that the endpoint is undocumented. A missing price record is reported as unavailable rather than inferred.
- Scheduled discount notifications now support Nintendo Taiwan digital watchlist entries in addition to Steam. Notifications require a matching TWD price record and a recognized sale state; unknown or failed price lookups preserve prior notification state rather than being treated as no sale. PS5 and link-only Nintendo entries remain unsupported for automated price notifications.
- The user reports that a live Discord smoke test succeeded, including the Nintendo discount notification flow. CI tests mock third-party responses and do not independently validate live endpoint reliability or permission.
- The Nintendo price and catalogue endpoints remain undocumented and **not yet approved for permitted automated reuse**. A successful live request is technical evidence only, not authorization. Review the applicable official terms/robots guidance and document the permitted use before treating this integration as production-approved; until then, keep it experimental and expect upstream changes or restrictions.

This integration addresses the user-visible mismatch between the working manual probe and the old link-only Discord command, while keeping the source-risk and digital-versus-physical distinction explicit.
