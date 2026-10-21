# Cloudflare Workers Discord Interactions (experimental)

This directory is an isolated migration path. It does not replace `bot.py`, change `main`, or alter any GitHub Actions workflows.

## Why this differs from bot.py

The existing bot uses `discord.py` and a persistent Discord Gateway connection. A Worker receives Discord HTTP Interactions instead; it must validate Ed25519 signatures and return the initial interaction response within Discord's deadline. It cannot run the current Python process unchanged.

## Required Worker secrets / variables

- `DISCORD_PUBLIC_KEY`: the application's public key from the Discord Developer Portal (not the bot token).
- `DISCORD_APPLICATION_ID`: Discord application ID, for command registration scripts/tools.
- `DISCORD_ADMIN_ID`: Discord user ID allowed to mutate the watchlist.
- `GITHUB_TOKEN`: fine-grained token scoped to this repository's Contents read/write access.
- `GITHUB_BRANCH`: use a dedicated test branch during development; do not default to main while testing.

Never commit secrets. Do not configure a production Worker until command parity and tests are complete.

## Current status

The migration is not production-ready yet. The full existing command surface to port is `/ping`, `/admincheck`, `/list`, `/add`, `/remove`, `/lookup`, and `/help`, including autocomplete behaviour for `/add`, `/remove`, and `/lookup`. Preserve the existing admin restriction, GitHub SHA-conflict retry behaviour, and NS/NS2 distinctions. The scheduled price-check, webhook, Healthchecks, and Nintendo catalogue workflows remain in GitHub Actions and must not be moved here.

## Deployment safety

1. Use a separate Cloudflare Worker and a non-production GitHub branch while testing.
2. Register slash commands only after the Worker handler and command definitions are ready.
3. Test Discord signature verification, unauthorized users, malformed payloads, GitHub API errors, concurrency conflicts, and all platform paths.
4. Confirm current Cloudflare pricing and account limits before deployment. A free tier is not a guarantee against all possible charges.
5. Do not merge this branch into `main` until tests pass and the user approves the cutover.
