import { memo, useId, useState, type ReactNode } from "react";
import { Badge, colors } from "@/shared/ui";
import { formatTimeAgo } from "@/shared/lib";
import {
  FIT_LABELS,
  FIT_TONES,
  NEW_LABEL,
  UNKNOWN_COMPANY,
  UNKNOWN_ROLE,
} from "../lib/constants";
import { formatCardSources, getTextPreview } from "../lib/helpers";
import type { Vacancy } from "../model/types";

interface VacancyCardProps {
  vacancy: Vacancy;
  /** Buttons rendered at the bottom of the card (open, dismiss, add…). */
  actions?: ReactNode;
}

/**
 * Display-only Inbox card: role, company, sources, posted date, fit badge +
 * reason and a 300-char text preview. "Show more" only expands the text; it
 * never changes the card's new/seen state. Text is rendered as plain text.
 */
export const VacancyCard = memo(function VacancyCard({ vacancy, actions }: VacancyCardProps) {
  const titleId = useId();
  const textId = useId();
  const [isExpanded, setIsExpanded] = useState(false);
  const { preview, isTruncated } = getTextPreview(vacancy.text);
  const isNew = vacancy.state === "new";

  return (
    <article
      aria-labelledby={titleId}
      style={{
        padding: "1rem",
        border: `1px solid ${colors.borderLight}`,
        borderLeft: `3px solid ${isNew ? colors.primary : colors.borderLight}`,
        borderRadius: "0.5rem",
        backgroundColor: colors.bgCard,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3
            id={titleId}
            style={{
              fontSize: "1rem",
              fontWeight: 600,
              color: colors.textPrimary,
              overflowWrap: "anywhere",
            }}
          >
            {vacancy.title ?? UNKNOWN_ROLE}
          </h3>
          <p style={{ fontSize: "0.875rem", color: colors.textSecondary }}>
            {vacancy.company ?? UNKNOWN_COMPANY}
          </p>
        </div>
        {isNew ? <Badge tone="accent">{NEW_LABEL}</Badge> : null}
      </div>

      <p
        style={{
          marginTop: "0.25rem",
          fontSize: "0.75rem",
          color: colors.textMuted,
          overflowWrap: "anywhere",
        }}
      >
        {formatCardSources(vacancy.sources)}
        {" · "}
        <time dateTime={vacancy.posted_at} title={new Date(vacancy.posted_at).toLocaleString()}>
          {formatTimeAgo(vacancy.posted_at)}
        </time>
      </p>

      {vacancy.fit ? (
        <p
          style={{
            marginTop: "0.5rem",
            display: "flex",
            alignItems: "baseline",
            gap: "0.5rem",
            fontSize: "0.875rem",
            color: colors.textSecondary,
          }}
        >
          <Badge tone={FIT_TONES[vacancy.fit]}>{FIT_LABELS[vacancy.fit]}</Badge>
          {vacancy.fit_reason ? <span>{vacancy.fit_reason}</span> : null}
        </p>
      ) : null}

      <p
        id={textId}
        style={{
          marginTop: "0.75rem",
          fontSize: "0.875rem",
          color: colors.textPrimary,
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
        }}
      >
        {isExpanded ? vacancy.text : preview}
      </p>
      {isTruncated ? (
        <button
          type="button"
          aria-expanded={isExpanded}
          aria-controls={textId}
          onClick={() => setIsExpanded((value) => !value)}
          style={{
            marginTop: "0.25rem",
            padding: 0,
            border: "none",
            background: "none",
            color: colors.primary,
            fontSize: "0.8125rem",
            cursor: "pointer",
          }}
        >
          {isExpanded ? "Show less" : "Show more"}
        </button>
      ) : null}

      {actions ? (
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {actions}
        </div>
      ) : null}
    </article>
  );
});
