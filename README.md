# Game Price Tracker

A Discord-managed game price tracker. The scheduled GitHub Actions workflow checks Steam prices in the Taiwan store and sends discount notifications to Discord.

## Current capabilities

- Discord slash commands: `/add`, `/remove`, `/list`, `/lookup`, `/help`, `/ping`, and `/admincheck`.
- `/lookup platform game` is the single current-price lookup command. Automated lookup currently exposes Steam, Nintendo Switch (NS), and Nintendo Switch 2 (NS2).
- Steam uses Taiwan-store search and current-price data. A Steam result without an explicit TWD currency is not displayed as a verified Taiwan price.
- NS and NS2 use cached Nintendo catalogue results and stable NSUIDs. Their current digital-price adapter calls an undocumented endpoint; this is experimental, and permission for automated reuse has **not** been confirmed.
- NS and NS2 remain distinct. Missing Nintendo platform metadata is shown as unverified; title similarity alone must not confirm a generation or edition.
- PS5 is out of scope for automated lookup and adding new watchlist entries. Existing manually maintained PS5 rows remain visible in `/list` and removable through `/remove`.
- Scheduled discount notifications are Steam-only. Non-Steam watchlist rows are skipped, not sent to Steam APIs.
- Notification state is stored in `notification_state.json`; invalid JSON stops the run rather than silently resetting notification state.
- Partial price-check failures produce a failed workflow status while successful notification state is still saved. GitHub watchlist updates re-read the current file and retry explicit SHA conflicts to reduce lost updates.

The product scope is current-price lookup and discount notifications only. Historical price collection, historical-price commands, and price-trend charts are out of scope. There is no separate `/price` or `/history` command.

## Platform and deployment direction

Current automated lookup is limited to **Steam, Nintendo Switch (NS), and Nintendo Switch 2 (NS2)**. PS5 is not an automated provider; legacy manually maintained rows are kept for reference and can be removed. NS, NS2, and NS2 Edition products must not be conflated based on title text alone.

The bot and scheduled checks should eventually run while the user's computer is turned off. That is a later deployment stage, not the current development setup. See [the platform and deployment roadmap](docs/platform-and-deployment-roadmap.md). Keep developing and testing locally until the feature set and sources are validated; do not infer that cloud hosting has been deployed.

## Watchlist format

Each entry identifies a platform-specific product:

```json
{
  "platform": "steam",
  "store": "steam",
  "product_id": "413150",
  "region": "TW",
  "name": "Stardew Valley"
}
```

Legacy Steam entries using `app_id` remain readable. New entries should use `product_id` and explicit `store` / `region` values. Notification-state keys are namespaced as `platform:store:region:product_id`.

## Price-source policy

Do not present unverified sources or inferred prices as directly observed current prices.

- **Steam:** the Steam App Details endpoint supplies current regional pricing. A numeric price must include the source-reported currency; the Taiwan lookup fails closed if currency is absent or is not TWD.
- **Nintendo Switch / Switch 2:** the current branch includes catalogue autocomplete and a Taiwan digital-price adapter for experimentation. The endpoints are undocumented and permitted automated reuse has not been confirmed. Results are labelled accordingly; this is not a claim of source approval. No physical retailer price is inferred from digital data.
- **PS5:** automated lookup is intentionally out of scope. Existing manual watchlist rows are references only and are not automatically checked.
- Never silently fall back to another region or mix digital and physical prices. NS, NS2, and NS2 Edition identities must remain distinct when source metadata is uncertain.

## Configuration

Discord bot environment variables:

- `DISCORD_BOT_TOKEN`
- `DISCORD_ADMIN_ID`
- `DISCORD_GUILD_ID`
- `GITHUB_TOKEN` (repository contents read/write access)

GitHub Actions repository secrets:

- `DISCORD_WEBHOOK_URL`
- `HEALTHCHECKS_PING_URL`

The repository workflow schedule is `6 12 * * *` (12:06 UTC / 20:06 Taiwan time). The separately configured cron-job.org trigger is not managed by this repository file.

## Nintendo source feasibility probe

A manual, low-rate probe for Nintendo Taiwan's candidate catalogue and digital-price endpoints is available at `scripts/probe_nintendo_sources.py`:

```bash
python scripts/probe_nintendo_sources.py
```

The probe searches the catalogue for selected titles and requests price data only for matching NSUIDs. It stores a local 24-hour catalogue cache at `.cache/nintendo_tw_catalogue.json` (ignored by Git). Use `--refresh-cache` to fetch the catalogue again or `--no-cache` to disable caching. The Discord Nintendo lookup reads this local cache; if it is missing or expired, autocomplete fails closed and asks you to refresh it:

```bash
python scripts/probe_nintendo_sources.py --refresh-cache
```

The probe does not run in CI. A successful response proves only that the endpoint responded at that time; it does not establish permission for automated reuse. See [the Nintendo source audit](docs/console-data-source-audit.md).

## Local checks

Install dependencies with `python -m pip install -r requirements.txt`, then run:

```bash
python -m compileall -q main.py bot.py nintendo.py nintendo_catalogue.py scripts tests
python -m unittest discover -s tests -v
```

A normal `python main.py` run requires the Discord webhook secret and live Steam access. Unit tests should use mocked provider responses and must not require live third-party services.
