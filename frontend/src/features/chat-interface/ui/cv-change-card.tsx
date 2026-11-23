import { memo, useId, useMemo, type CSSProperties } from "react";
import type { ChangeCard, ChangeCardState } from "@/entities/chat";
import { Badge, Button, colors, fonts } from "@/shared/ui";
import { buildCardDiff, markAllLines } from "../lib/build-diff-rows";
import { getInsertLabel } from "../lib/card-labels";
import { useCardDecision } from "../model/use-card-decision";
import { DiffLinesView } from "./diff-lines-view";

interface CvChangeCardProps {
  applicationId: string;
  card: ChangeCard;
  onCardUpdated: (card: ChangeCard) => void;
}

const CARD_BORDER: Record<ChangeCardState, string> = {
  pending: colors.border,
  accepted: colors.success,
  rejected: colors.borderLight,
  stale: colors.badge.warning.text,
};

const SMALL_BUTTON: CSSProperties = {
  fontSize: "0.75rem",
  padding: "0.25rem 0.75rem",
};

function CardBody({ card }: { card: ChangeCard }) {
  const { op, before_text: beforeText, after_text: afterText } = card;
  const diff = useMemo(
    () => (op === "replace" ? buildCardDiff(beforeText, afterText) : null),
    [op, beforeText, afterText],
  );

  if (diff) {
    return (
      <>
        <DiffLinesView label="Before" rows={diff.before} />
        <DiffLinesView label="After" rows={diff.after} />
      </>
    );
  }
  if (op === "insert") {
    return (
      <DiffLinesView
        label={getInsertLabel(card)}
        rows={markAllLines(afterText, "added")}
      />
    );
  }
  return (
    <DiffLinesView label="Removed" rows={markAllLines(beforeText, "removed")} />
  );
}

function StateBadge({ state }: { state: ChangeCardState }) {
  switch (state) {
    case "accepted":
      return (
        <Badge tone="success">
          <span aria-hidden="true" style={{ marginRight: "0.25rem" }}>
            ✓
          </span>
          Accepted
        </Badge>
      );
    case "rejected":
      return <Badge tone="neutral">Rejected</Badge>;
    case "stale":
      return <Badge tone="warning">Stale</Badge>;
    case "pending":
      return null;
  }
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
        <span
          id={titleId}
          style={{ fontWeight: 600, color: colors.textPrimary }}
        >
          CV text
        </span>
        <StateBadge state={card.state} />
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
            style={SMALL_BUTTON}
            disabled={card.state === "stale" || running !== null}
            loading={running === "accept"}
            onClick={() => void decide("accept")}
          >
            Accept
          </Button>
          <Button
            variant="secondary"
            style={SMALL_BUTTON}
            disabled={running !== null}
            loading={running === "reject"}
            onClick={() => void decide("reject")}
          >
            Reject
          </Button>
        </div>
      )}

      {error && (
        <p
          role="alert"
          style={{ margin: 0, color: colors.error, fontSize: "0.8125rem" }}
        >
          {error}
        </p>
      )}
    </article>
  );
});
