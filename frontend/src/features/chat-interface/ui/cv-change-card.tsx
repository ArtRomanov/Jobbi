import { memo, useCallback, useId, useRef } from "react";
import type { ChangeCard } from "@/entities/chat";
import { Button, colors, fonts } from "@/shared/ui";
import { getCardActionLabel, getCardTitle } from "../lib/card-labels";
import { CARD_BORDER, CARD_BUTTON_STYLE } from "../lib/card-styles";
import { useCardDecision, type CardDecision } from "../model/use-card-decision";
import { CardBody } from "./card-body";
import { CardStateBadge } from "./card-state-badge";

interface CvChangeCardProps {
  applicationId: string;
  card: ChangeCard;
  /** 1-based position of the card within its message ("change 2"). */
  number: number;
  onCardUpdated: (card: ChangeCard) => void;
}

/**
 * A proposed CV text edit in the chat (spec 011 §2.7): before/after with a
 * line diff, Accept/Reject while Pending (Reject only while Stale), and an
 * inline error under the card when a decision fails.
 */
export const CvChangeCard = memo(function CvChangeCard({
  applicationId,
  card,
  number,
  onCardUpdated,
}: CvChangeCardProps) {
  const titleId = useId();
  const titleRef = useRef<HTMLSpanElement>(null);
  const { running, error, decide } = useCardDecision(
    applicationId,
    card,
    onCardUpdated,
  );
  const isOpen = card.state === "pending" || card.state === "stale";
  const isRejected = card.state === "rejected";

  // The pressed button is disabled or removed once the decision lands, so
  // focus goes to the card title instead of falling back to <body>.
  const handleDecision = useCallback(
    async (decision: CardDecision): Promise<void> => {
      await decide(decision);
      titleRef.current?.focus();
    },
    [decide],
  );

  return (
    <article
      aria-labelledby={titleId}
      data-state={card.state}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        padding: "0.75rem",
        borderRadius: "0.5rem",
        border: `1px solid ${CARD_BORDER[card.state]}`,
        borderLeftWidth: "4px",
        backgroundColor: colors.bgCard,
        fontFamily: fonts.base,
        fontSize: "0.875rem",
        opacity: isRejected ? 0.65 : 1,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.5rem",
        }}
      >
        <span
          id={titleId}
          ref={titleRef}
          tabIndex={-1}
          style={{ fontWeight: 600, color: colors.textPrimary }}
        >
          {getCardTitle(number)}
        </span>
        {/* Always mounted, so screen readers announce the new state */}
        <span role="status">
          <CardStateBadge state={card.state} />
        </span>
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          textDecoration: isRejected ? "line-through" : undefined,
        }}
      >
        <CardBody card={card} />
      </div>

      {isOpen && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <Button
            style={CARD_BUTTON_STYLE}
            aria-label={getCardActionLabel("Accept", number)}
            disabled={card.state === "stale" || running !== null}
            loading={running === "accept"}
            onClick={() => void handleDecision("accept")}
          >
            Accept
          </Button>
          <Button
            variant="secondary"
            style={CARD_BUTTON_STYLE}
            aria-label={getCardActionLabel("Reject", number)}
            disabled={running !== null}
            loading={running === "reject"}
            onClick={() => void handleDecision("reject")}
          >
            Reject
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" style={{ margin: 0, color: colors.error, fontSize: "0.8125rem" }}>
          {error}
        </p>
      )}
    </article>
  );
});
