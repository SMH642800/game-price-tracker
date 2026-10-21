# Cloudflare Workers Discord Interactions (experimental)

This is an isolated migration path. It does not replace `bot.py`, change `main`, or alter GitHub Actions workflows. Do not merge this branch to `main` yet.

## Current implementation

- `worker.js`: Ed25519 request-signature validation, PING acknowledgement, `/ping`, `/admincheck`, `/help`, `/list`, `/add`, `/remove`, and `/lookup` handlers.
- `commands.json`: Discord application command definitions for registering the seven slash commands, including autocomplete.
- Slow `/list`, `/add`, `/remove`, and `/lookup` handlers defer immediately and send an ephemeral follow-up.
- The Worker uses GitHub Contents API to read/write `games_track_list.json`; set `GITHUB_BRANCH=feature/cloudflare-interactions` during testing.
- Scheduled daily price checks, webhook notifications, Healthchecks, and weekly Nintendo catalogue refresh remain in GitHub Actions.

## Important limitations before production

This is an initial port and **has not yet been runtime-tested or approved for production**.

- `/remove` now attempts to clean matching entries from `notification_state.json` after removing watchlist rows. If cleanup fails, the watchlist removal remains committed and the command reports a warning; inspect Worker Logs before retrying.
- The Worker reads the public weekly Nintendo catalogue cache from `main`; the cache must be valid and fresh. The cache was found empty during the 2026-10-21 review, so Nintendo autocomplete and lookup will fail until the weekly catalogue refresh succeeds. The existing Python implementation also supports a curated fallback and optional HK cache, which this Worker port does not fully reproduce.
- The existing Python provider adapters contain stricter validation and error handling than the first Worker port. Price results must be tested against real API responses before relying on them.
- GitHub SHA conflicts are retried for watchlist and notification-state writes, but concurrency behaviour still needs testing. The GitHub token must have repository Contents read/write access. Writes are hard-blocked unless the effective target branch is exactly `feature/cloudflare-interactions`.
- Discord interaction tokens expire; verify follow-up handling under slow provider/API responses.
- Do not expose the Worker to production commands until the full test checklist passes.

## Required Worker variables / secrets

- `DISCORD_PUBLIC_KEY`: application public key from Discord Developer Portal (not the bot token).
- `DISCORD_APPLICATION_ID`: Discord application ID, used to send interaction follow-ups.
- `DISCORD_ADMIN_ID`: Discord user ID allowed to add/remove tracked games.
- `GITHUB_TOKEN`: fine-grained token scoped to this repository's Contents read/write access.
- `GITHUB_BRANCH`: set to `feature/cloudflare-interactions` while testing.

Never commit secrets. Use Cloudflare's secret/variable settings, not source code.

## Safe testing sequence

1. Keep Railway available as rollback until the Worker passes tests; only one Discord application endpoint should be active for a given application at a time.
2. Create a separate Cloudflare Worker for this branch and set the variables above.
3. Configure Discord's Interactions Endpoint URL to the Worker's HTTPS URL. Discord validates it using a signed PING request.
4. Register application commands using `commands.json` against the test application/guild. Do not register against the production application until explicitly ready.
5. Test signature rejection, PING, all seven commands, autocomplete, admin authorization, malformed inputs, GitHub API failures, concurrent watchlist updates, Steam and Nintendo responses, and stale catalogue behaviour.
6. Confirm current Cloudflare pricing and account limits before deployment. Free-tier limits do not guarantee every usage pattern is free.
7. Do not merge this branch into `main` or retire Railway until tests pass and the user approves the cutover.
