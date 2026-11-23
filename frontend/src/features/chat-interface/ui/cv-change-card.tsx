import { memo, useId } from "react";
import type { ChangeCard } from "@/entities/chat";
import { Button, colors, fonts } from "@/shared/ui";
import { CARD_BORDER, CARD_BUTTON_STYLE } from "../lib/card-styles";
import { useCardDecision } from "../model/use-card-decision";
import { CardBody } from "./card-body";
import { CardStateBadge } from "./card-state-badge";

interface CvChangeCardProps {
  applicationId: string;
  card: ChangeCard;
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
  onCardUpdated,
}: CvChangeCardProps) {
  const titleId = useId();
  const { running, error, decide } = useCardDecision(
    applicationId,
    card,
    onCardUpdated,
  );
  const isOpen = card.state === "pending" || card.state === "stale";
  const isRejected = card.state === "rejected";

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
        <span id={titleId} style={{ fontWeight: 600, color: colors.textPrimary }}>
          CV text
        </span>
        <CardStateBadge state={card.state} />
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
            disabled={card.state === "stale" || running !== null}
            loading={running === "accept"}
            onClick={() => void decide("accept")}
          >
            Accept
          </Button>
          <Button
            variant="secondary"
            style={CARD_BUTTON_STYLE}
            disabled={running !== null}
            loading={running === "reject"}
            onClick={() => void decide("reject")}
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
