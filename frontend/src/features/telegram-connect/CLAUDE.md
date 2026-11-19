# Telegram Connect Feature

Settings-page section (`TelegramSection`) for linking the user's Telegram account to the shared Jobbi bot via a one-time code, and for disconnecting.

- State machine lives in `model/use-telegram-connection.ts` (`loading → not-connected → awaiting-link → connected`).
- While a code is shown, status is polled every 3s with chained timeouts; polling stops on link, code expiry, cancel, or unmount.
- The API does not expose the bot's @username, so instructions say "the Jobbi bot" (`lib/constants.ts`).
- `expires_at` arrives as naive UTC — always parse with `parseUtcDate`.
