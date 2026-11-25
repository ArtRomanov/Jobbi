import { memo } from "react";
import { CvTailoredFor, isTailoredCv, type Cv } from "@/entities/cv";
import { MakeBaseButton } from "@/features/cv-make-base";
import { Badge, Button, ButtonLink, colors } from "@/shared/ui";
import { BASE_LABEL, TAILORED_FOR_PREFIX } from "../lib/constants";
import { formatCvDate, formatLinkedCount, getCvActionLabel } from "../lib/helpers";
import type { CvRowActions } from "../model/types";

interface CvRowProps extends CvRowActions {
  cv: Cv;
  isDuplicating: boolean;
  isDownloading: boolean;
  isDownloadingHtml: boolean;
  isDeleting: boolean;
}

/**
 * One CV on the CVs page: name (+ "Base" label), the application a tailored
 * copy was made for, and the actions. "Make base" is shown on every non-base CV.
 */
export const CvRow = memo(function CvRow({
  cv,
  isDuplicating,
  isDownloading,
  isDownloadingHtml,
  isDeleting,
  onDuplicate,
  onDownload,
  onDownloadHtml,
  onDelete,
  onMadeBase,
}: CvRowProps) {
  const isTailored = isTailoredCv(cv);
  return (
    <li
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1rem",
        flexWrap: "wrap",
        padding: "0.75rem 0",
        borderBottom: `1px solid ${colors.borderLight}`,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
          <span
            style={{
              fontWeight: 600,
              fontSize: "0.875rem",
              color: colors.textPrimary,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {cv.name}
          </span>
          {cv.is_base ? <Badge tone="accent">{BASE_LABEL}</Badge> : null}
        </div>
        {isTailored ? (
          <div style={{ fontSize: "0.8125rem", marginTop: "0.125rem", color: colors.textSecondary }}>
            {TAILORED_FOR_PREFIX} <CvTailoredFor cv={cv} />
          </div>
        ) : null}
        <div style={{ fontSize: "0.75rem", color: colors.textMuted, marginTop: "0.125rem" }}>
          Updated {formatCvDate(cv.updated_at)}
          {cv.linked_applications_count > 0 ? (
            <span>
              {" · "}
              {formatLinkedCount(cv.linked_applications_count)}
            </span>
          ) : null}
        </div>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", flexShrink: 0 }}>
        {cv.is_base ? null : <MakeBaseButton cv={cv} onMadeBase={onMadeBase} />}
        <ButtonLink
          to={`/cvs/${cv.id}/edit`}
          variant="secondary"
          aria-label={getCvActionLabel("edit", cv.name)}
        >
          Edit
        </ButtonLink>
        <Button
          type="button"
          variant="secondary"
          aria-label={getCvActionLabel("duplicate", cv.name)}
          loading={isDuplicating}
          onClick={() => onDuplicate(cv)}
        >
          Duplicate
        </Button>
        <Button
          type="button"
          variant="secondary"
          aria-label={getCvActionLabel("pdf", cv.name)}
          loading={isDownloading}
          onClick={() => onDownload(cv)}
        >
          PDF
        </Button>
        <Button
          type="button"
          variant="secondary"
          aria-label={getCvActionLabel("html", cv.name)}
          loading={isDownloadingHtml}
          onClick={() => onDownloadHtml(cv)}
        >
          HTML
        </Button>
        <Button
          type="button"
          variant="secondary"
          aria-label={getCvActionLabel("delete", cv.name)}
          style={{ color: colors.error, borderColor: colors.error }}
          loading={isDeleting}
          onClick={() => onDelete(cv)}
        >
          Delete
        </Button>
      </div>
    </li>
  );
});
