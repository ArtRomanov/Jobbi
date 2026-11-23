import { useCallback, useState } from "react";
import {
  acceptChangeCard,
  getChatHistory,
  rejectChangeCard,
  type ChangeCard,
} from "@/entities/chat";
import { useToast } from "@/shared/ui";
import {
  CARD_ERROR_MESSAGES,
  getCardErrorCode,
} from "../lib/card-error-message";
import { CARD_ACCEPTED_MESSAGE } from "../lib/constants";

export type CardDecision = "accept" | "reject";

export interface CardDecisionState {
  /** The decision whose request is running, or null. */
  running: CardDecision | null;
  /** Inline error under the card, or null. */
  error: string | null;
  decide: (decision: CardDecision) => Promise<void>;
}

/** The card's current state from the server (used after `CARD_DECIDED`). */
async function fetchFreshCard(
  applicationId: string,
  cardId: string,
): Promise<ChangeCard | null> {
  const history = await getChatHistory(applicationId);
  for (const message of history) {
    const found = message.cards?.find((card) => card.id === cardId);
    if (found) return found;
  }
  return null;
}

/**
 * Accept / Reject for one card. Each card owns its own request, so cards are
 * decided independently. The new card goes up through `onCardUpdated`; the
 * error stays local to the card.
 */
export function useCardDecision(
  applicationId: string,
  card: ChangeCard,
  onCardUpdated: (card: ChangeCard) => void,
): CardDecisionState {
  const [running, setRunning] = useState<CardDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { showToast } = useToast();

  const decide = useCallback(
    async (decision: CardDecision): Promise<void> => {
      setRunning(decision);
      setError(null);
      try {
        const updated =
          decision === "accept"
            ? await acceptChangeCard(applicationId, card.id)
            : await rejectChangeCard(applicationId, card.id);
        onCardUpdated(updated);
        // Accept saved the CV; Reject saves nothing, so no toast for it
        if (decision === "accept") showToast(CARD_ACCEPTED_MESSAGE, "success");
      } catch (err: unknown) {
        const code = getCardErrorCode(err);
        const fallback =
          decision === "accept"
            ? CARD_ERROR_MESSAGES.ACCEPT_FAILED
            : CARD_ERROR_MESSAGES.REJECT_FAILED;
        switch (code) {
          case "CARD_STALE":
            onCardUpdated({ ...card, state: "stale" });
            setError(CARD_ERROR_MESSAGES.CARD_STALE);
            break;
          case "PASSAGE_NOT_UNIQUE":
            setError(CARD_ERROR_MESSAGES.PASSAGE_NOT_UNIQUE);
            break;
          case "TOO_LONG":
            setError(CARD_ERROR_MESSAGES.TOO_LONG);
            break;
          case "CV_BUSY":
            // The CV kept changing during the Accept; the card stays pending
            setError(CARD_ERROR_MESSAGES.ACCEPT_FAILED);
            break;
          case "CARD_DECIDED": {
            // Decided elsewhere (another tab): show the real state, no error.
            const fresh = await fetchFreshCard(applicationId, card.id).catch(
              () => null,
            );
            if (fresh) onCardUpdated(fresh);
            else setError(fallback);
            break;
          }
          default:
            setError(fallback);
        }
      } finally {
        setRunning(null);
      }
    },
    [applicationId, card, onCardUpdated, showToast],
  );

  return { running, error, decide };
}
