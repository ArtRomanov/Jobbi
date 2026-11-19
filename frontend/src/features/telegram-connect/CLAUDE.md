# Telegram Connect Feature

Settings-page section (`TelegramSection`) for linking the user's Telegram account to the shared Jobbi bot via a one-time code, and for disconnecting.

- State machine lives in `model/use-telegram-connection.ts` (`loading → not-connected → awaiting-link → connected`).
- While a code is shown, status is polled every 3s with chained timeouts; polling stops on link, code expiry, cancel, or unmount.
- Expiry is timed as `CODE_TTL_MS` from when the code arrived (+ `EXPIRY_GRACE_MS`), never from `expires_at`, so client clock skew can't cut the window short. Expiry and Cancel both run one final status check so a just-made link isn't lost.
- The API does not expose the bot's @username, so instructions say "the Jobbi bot" (`lib/constants.ts`).
- The "Code expires at" label also uses receipt + `CODE_TTL_MS` (user's clock). `expires_at` is only a NaN sanity check; it may be Z-suffixed or naive UTC — always parse with `parseUtcDate`.
