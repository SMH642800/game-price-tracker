# Game Price Tracker

A Discord-managed game price tracker. The scheduled GitHub Actions workflow currently checks Steam prices in the Taiwan store and sends discount notifications to Discord.

## Current capabilities

- Discord slash commands: `/add`, `/remove`, `/list`, `/price`, `/help`, `/ping`, and `/admincheck`.
- `/add` and `/remove` ask for a platform first. Steam has live search and price checking; PS5, Nintendo Switch (NS), and Nintendo Switch 2 use title-based lookup and watchlist tracking.
- `/lookup platform game` returns live Steam prices for Steam, and store plus web price-search links for PS5/NS/NS2. Console links are references, not verified numeric prices.
- Notification state is stored in `notification_state.json`; corrupted JSON stops the run rather than silently resetting notification state.
- `/price` fetches the current Taiwan Steam price.
- Partial price-check failures produce a failed workflow status while successfully sent notification state is still saved.
- GitHub watchlist updates re-read the current file and retry SHA conflicts to reduce lost updates.

The product scope is current-price lookup and discount notifications only. Historical price collection, historical-price commands, and price-trend charts are out of scope.

## Platform and deployment direction

The roadmap covers **Steam, PS5, Nintendo Switch (NS), and Nintendo Switch 2 (NS2)**. NS and NS2 must be represented separately; the same game title can map to distinct platform products, editions, upgrade paths, and prices. Do not merge NS, NS2, and NS2 Edition prices based on title text alone.

The system is also intended to run independently of a personal computer. See [the platform and cloud deployment roadmap](docs/platform-and-deployment-roadmap.md) for architecture constraints and staged deployment guidance. These are design requirements, not claims that all platforms or cloud hosting are already implemented.

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

## Price-source policy

The Bot must not present unverified sources or inferred prices as directly observed current prices.

- **Steam:** Steam App Details provides current price. `/price` fetches the current Taiwan-store price.
- **PS5, NS, and NS2:** v1 supports title-based tracking plus store and web price-search links, without inventing product IDs or numeric prices. Console links are references, not verified numeric prices. For Nintendo, digital and physical prices must remain separate, and every price must identify its region, currency, product/edition, source, and retrieval time. Automated numeric console pricing remains disabled until reliable sources and permitted use are verified. A first isolated Nintendo digital-price adapter and mocked tests exist on the PR branch, but they are not wired into Discord commands. Physical game prices require a separate approved retailer source.

Legacy Steam entries using `app_id` remain readable. New entries should use `product_id` and explicit `store` / `region` values. Notification-state keys are namespaced as `platform:store:region:product_id`.

## Configuration

Discord bot environment variables:

- `DISCORD_BOT_TOKEN`
- `DISCORD_ADMIN_ID`
- `DISCORD_GUILD_ID`
- `GITHUB_TOKEN` (needs repository contents read/write access)

GitHub Actions repository secrets:

- `DISCORD_WEBHOOK_URL`
- `HEALTHCHECKS_PING_URL`

The existing GitHub Actions schedule remains `6 12 * * *` (12:06 UTC / 20:06 Taiwan time). The separately configured cron-job.org trigger is not managed by this repository file.

## Nintendo source feasibility probe

A manual, low-rate probe for Nintendo Taiwan's candidate catalogue and digital-price endpoints is available at `scripts/probe_nintendo_sources.py`. Run it locally with network access:

```bash
python scripts/probe_nintendo_sources.py
```

It searches the catalogue for 時之笛 and 亰都幻都 / Kyoto Xanadu, then requests price data only for matching NSUIDs. To avoid downloading all pages on every development run, it stores a local 24-hour catalogue cache at `.cache/nintendo_tw_catalogue.json` (ignored by Git). Use `--refresh-cache` to fetch the catalogue again or `--no-cache` to disable caching. The output includes cache status, duplicate NSUID counts, and elapsed-time diagnostics. It does not run in CI or enable numeric prices in Discord. The endpoints are undocumented and automated reuse permissions have not been confirmed; a successful probe is technical evidence only, not approval to enable production automation. See `docs/console-data-source-audit.md` for the current source gates.

## Local checks

Install dependencies with `python -m pip install -r requirements.txt`, then run `python -m unittest discover -s tests -v`. A normal `python main.py` run requires the Discord webhook secret and live Steam access.
