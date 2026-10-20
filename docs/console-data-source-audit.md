# Nintendo catalogue and price-source audit

Status: **source verification and permitted-use review pending** (2026-10-20)

This document tracks the Nintendo catalogue and digital-price integrations currently present on the feature branch. A successful HTTP response or a matching price record does not establish endpoint stability, accuracy, or permission for automated reuse.

## Scope

- Interactive lookup currently supports Steam, Nintendo Switch (NS), and Nintendo Switch 2 (NS2).
- PS5 automated lookup is intentionally out of scope. Existing manually maintained PS5 watchlist rows are only legacy references and are not automatically queried.
- Scheduled discount notifications remain Steam-only.
- Nintendo digital lookup is an experimental interactive path. Do not enable scheduled Nintendo checks or claim source approval based only on the current probe.

## Current implementation

- `scripts/probe_nintendo_sources.py` manually probes candidate Nintendo Taiwan catalogue and price endpoints.
- `nintendo_catalogue.py` reads a local 24-hour cache and returns catalogue matches with stable NSUIDs. It does not crawl the catalogue during Discord autocomplete.
- `nintendo.py` queries the candidate digital-price endpoint by exact NSUID and requested region. It does not intentionally fall back to another region or use physical retailer prices.
- `bot.py` connects the experimental Nintendo adapter to `/lookup` and `/add`; results label the source as an undocumented interface. Missing platform metadata is visibly unverified.
- Scheduled `main.py` checks Steam only and skips non-Steam watchlist entries.

## Candidate-source gates

### Nintendo Taiwan catalogue

Before relying on the catalogue in production, verify using official documentation or reproducible manual checks:

1. Whether the endpoint is officially supported for public or automated use.
2. Whether automated access, local caching, and the intended query frequency are permitted by the relevant terms and robots guidance.
3. Whether returned product identifiers are stable and uniquely identify the exact software product/edition.
4. Whether platform metadata distinguishes original Switch, Switch 2, and Switch 2 Edition consistently.
5. How missing metadata, delisted titles, pagination changes, and duplicate IDs should be handled.

A catalogue match identifies a candidate product; it does not prove that a price record is valid for that product.

### Nintendo digital price

Before treating the numeric result as a production price source, verify:

1. Official documentation or authoritative confirmation of the endpoint's intended use.
2. Whether automated reuse, caching, and request rates are permitted.
3. Whether the requested `country=TW` response corresponds to a Taiwan consumer digital price.
4. Whether `title_id`, sales status, currency, regular price, and discount price are stable and well-defined.
5. Whether the returned price is tied to the exact digital product/edition and how preorder, unavailable, delisted, and missing-price records are represented.

The current adapter fails closed for a missing or mismatched regional currency and does not infer a price from another region. These safeguards do not substitute for source approval.

### Physical Nintendo prices

Physical card/cartridge prices require a separate retailer source. Before implementing one, verify:

- official or documented access method and permission for automated use;
- exact product/edition identity and retailer;
- Taiwan availability, TWD price, stock status, and retrieval timestamp;
- attribution, rate limits, caching rules, and acceptable request volume.

Never derive a physical price from an eShop record, use search snippets as verified offers, or combine prices across regions.

## Validation requirements

- Unit tests mock all provider responses and do not require live third-party services.
- Cover duplicate NSUIDs, duplicate titles, missing platform metadata, NS/NS2 separation, wrong-region currency, missing currency, negative/non-finite amounts, unavailable status, malformed JSON, HTTP errors, timeouts, and cache expiry.
- Keep live source smoke tests manual and low-rate; record the date, region, product ID, response shape, and observed caveats.
- Record source documentation/terms URLs and the outcome of the permitted-use review before calling a source approved.
- Until these gates pass, keep the Nintendo source caveat visible and do not add Nintendo to scheduled notifications.

## Current decision

**No Nintendo catalogue or numeric price provider is approved for production reuse yet.** The current code is an experimental, explicitly caveated lookup path. The probe establishes only the observed behaviour at the time it is run. Continue to fail closed when the cache, product identity, price record, or currency is missing or inconsistent.
