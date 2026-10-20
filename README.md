# Game Price Tracker

A Discord-managed game price tracker. The scheduled GitHub Actions workflow currently checks Steam prices in the Taiwan store and sends discount notifications to Discord.

## Current capabilities

- Discord slash commands: `/add`, `/remove`, `/list`, `/price`, `/history`, `/help`, `/ping`, and `/admincheck`.
- `/add` and `/remove` ask for a platform first. Steam has live search and price checking.
- PS5 and Nintendo Switch 2 platform identifiers are reserved in the data model and command menus, but their live store search and price providers are not enabled until a reliable Taiwan-region source is verified.
- Notification state is stored in `notification_state.json`; corrupted JSON stops the run rather than silently resetting history.
- `price_history.json` stores up to 365 daily Taiwan-store price observations per product; same-day checks replace that day's sample.
- `/price` fetches the current Taiwan Steam price. `/history` displays recorded observations and the lowest price observed since tracking began.
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

Historical-price limitation: Steam App Details provides current price, not a complete historical price series. This project records prices from the first successful scheduled check onward. Backfilling older prices requires a separate historical data provider (for example, an API with its own access/key/terms); third-party data should not be assumed complete or free.

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
