# Game Price Tracker

A Discord-managed game price tracker. The scheduled GitHub Actions workflow currently checks Steam prices in the Taiwan store and sends discount notifications to Discord.

## Current capabilities

- Discord slash commands: `/add`, `/remove`, `/list`, `/price`, `/history`, `/help`, `/ping`, and `/admincheck`.
- `/add` and `/remove` ask for a platform first. Steam has live search and price checking.
- PS5 and Nintendo Switch 2 platform identifiers are reserved in the data model and command menus, but their live store search and price providers are not enabled until a reliable Taiwan-region source is verified.
- Notification state is stored in `notification_state.json`; corrupted JSON stops the run rather than silently resetting history.
- `price_history.json` stores up to 365 daily Taiwan-store price observations per product; same-day checks replace that day's sample.
- `/price` fetches the current Taiwan Steam price. `/history` displays recorded observations and the lowest price observed since tracking began, and links to the matching SteamDB app page for broader historical context.
- Partial price-check failures produce a failed workflow status while successfully sent notification state is still saved.
- GitHub watchlist updates re-read the current file and retry SHA conflicts to reduce lost updates.

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

Historical-price policy: this project separates prices observed directly by the Bot from historical information published by external price-tracking websites. The Bot must not label third-party estimates as its own observations, silently combine the two datasets, or invent missing historical values.

- **Steam:** Steam App Details provides current price, not a complete historical price series. This project records prices from the first successful scheduled check onward. `/history` links to the matching [SteamDB app page](https://steamdb.info/) for broader historical context.
- **PS5 and Nintendo Switch 2:** if platform support is added, historical-price context will come from suitable external reference websites rather than an assumed complete local history. A source must be checked for the correct game/version and region before its link or data is presented. These platforms remain disabled for automated store search and price checking until a reliable Taiwan-region current-price source is verified.

SteamDB research note: its [FAQ](https://steamdb.info/faq/) does not offer a generally available public API for this use and disallows unapproved automated scraping. Therefore this project links to SteamDB instead of scraping or importing its data. Direct historical-data import should only be considered if SteamDB provides explicit permission or a supported access method. Do not present SteamDB values as locally verified samples or silently mix them with this Bot's observations.

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

## Local checks

Install dependencies with `python -m pip install -r requirements.txt`, then run `python -m unittest discover -s tests -v`. A normal `python main.py` run requires the Discord webhook secret and live Steam access.
