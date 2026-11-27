import { memo, useCallback, useId, useRef } from "react";
import type { ChangeCard } from "@/entities/chat";
import { Button, colors, fonts } from "@/shared/ui";
import {
  CARD_OUTDATED_LABEL,
  getCardActionLabel,
  getCardTitle,
} from "../lib/card-labels";
import { CARD_BORDER, CARD_BUTTON_STYLE } from "../lib/card-styles";
import { useCardDecision, type CardDecision } from "../model/use-card-decision";
import { CardBody } from "./card-body";
import { CardStateBadge } from "./card-state-badge";
import { CardWarning } from "./card-warning";

interface CvChangeCardProps {
  applicationId: string;
  card: ChangeCard;
  /** 1-based position of the card within its message ("change 2"). */
  number: number;
  /**
   * The card's reply is no longer the newest message: no Accept/Reject, and a
   * pending card says so. Accepted/Rejected/Stale keep their badges.
   */
  outdated?: boolean;
  onCardUpdated: (card: ChangeCard) => void;
}

/**
 * A proposed CV text edit in the chat (spec 011 §2.7): before/after with a
 * line diff, the server's warning if any (Accept stays enabled), Accept/Reject
 * while Pending (Reject only while Stale), and an inline error under the card
 * when a decision fails. Cards of an older reply
 * (`outdated`) have no buttons.
 */
export const CvChangeCard = memo(function CvChangeCard({
  applicationId,
  card,
  number,
  outdated = false,
  onCardUpdated,
}: CvChangeCardProps) {
  const titleId = useId();
  const warningId = useId();
  const titleRef = useRef<HTMLSpanElement>(null);
  const { running, error, decide } = useCardDecision(
    applicationId,
    card,
    onCardUpdated,
  );
  const isOpen =
    !outdated && (card.state === "pending" || card.state === "stale");
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
          {getCardTitle(number, card.op)}
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

      {card.warning ? <CardWarning id={warningId} text={card.warning} /> : null}

      {isOpen && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <Button
            style={CARD_BUTTON_STYLE}
            aria-label={getCardActionLabel("Accept", number)}
            aria-describedby={card.warning ? warningId : undefined}
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

      {outdated && card.state === "pending" && (
        <p style={{ margin: 0, color: colors.textMuted, fontSize: "0.8125rem" }}>
          {CARD_OUTDATED_LABEL}
        </p>
      )}

      {error && (
        <p role="alert" style={{ margin: 0, color: colors.error, fontSize: "0.8125rem" }}>
          {error}
        </p>
      )}
    </article>
  );
});
