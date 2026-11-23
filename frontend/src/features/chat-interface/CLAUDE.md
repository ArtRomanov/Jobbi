# Chat Interface Feature

User-facing chat UI components for the AI assistant. Contains MessageBubble, ChatInput, QuickActionBar, and ChatWindow. Quick-action templates live in lib/constants.ts. Composed at the page level by pages/chat.

- **CV change cards** (spec 011 §2.7): `ui/cv-change-card.tsx` renders one `ChangeCard` titled "CV text". Replace → "Before"/"After" columns from `diffLines` (`lib/build-diff-rows.ts`); insert → only the added lines, labelled by `lib/card-labels.ts`; remove → only the removed lines, "Removed". Removed/added lines differ by colour **and** by a `−`/`+` marker, `<del>`/`<ins>` and a screen-reader prefix.
- `ChatWindow` renders each message's `cards` right under its bubble (`ui/card-list.tsx`), plus `streamingCards` under the reply being streamed. Card updates go up through `onCardUpdated`; the page swaps them in with `replaceCardInMessages`.
- `model/use-card-decision.ts`: one request per card (cards are decided independently; both buttons disabled while it runs). Errors map from `{"detail": "<CODE>"}` in `lib/card-error-message.ts`: `CARD_STALE` also marks the card Stale (Accept disabled, Reject still works); `CARD_DECIDED` re-reads the card from `GET /chat` and shows its real state without an error; 5xx / network / unknown → the generic text.
