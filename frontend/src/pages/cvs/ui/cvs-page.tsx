import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listCvs, deleteCv, duplicateCv, groupCvs, type Cv } from "@/entities/cv";
import { CV_HTML_DOWNLOAD_ERROR_MESSAGE, downloadCvHtml } from "@/features/cv-html-export";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { UploadCvButton } from "@/features/cv-upload";
import { PageCard, PageHeader, Button, colors, useToast } from "@/shared/ui";
import { handleApiError } from "@/shared/api";
import {
  MY_CVS_TITLE,
  NO_BASE_HINT,
  NO_CVS_TEXT,
  PAGE_SUBTITLE,
  PAGE_TITLE,
  CV_DELETED_MESSAGE,
  CV_DUPLICATED_MESSAGE,
  REFRESH_ERROR_MESSAGE,
  TAILORED_TITLE,
} from "../lib/constants";
import { CvList } from "./cv-list";
import { CvSection } from "./cv-section";

const MUTED_TEXT_STYLE = { color: colors.textMuted, fontSize: "0.875rem" } as const;

/**
 * CVs page (spec 011 §2.4–2.5): "My CVs" (base first, with a "Base" label)
 * and "Tailored for applications" (hidden when empty), each CV with Make base
 * (non-base only), Edit, Duplicate, PDF, HTML and Delete. Lives in `pages/` because
 * it is a route; it composes the upload and make-base features.
 */
export function CvsPage() {
  const [cvs, setCvs] = useState<Cv[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadingHtmlId, setDownloadingHtmlId] = useState<string | null>(null);
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);
  const { showToast } = useToast();

  // Each load gets a number; only the latest one may touch state, so an older
  // response that arrives late never overwrites a newer list
  const latestRequestRef = useRef(0);
  const hasListRef = useRef(false);

  // Only the first load shows "Loading..." and, on failure, the error in place
  // of the list. A failed refresh keeps the list on screen and shows a toast.
  const fetchCvs = useCallback(async () => {
    latestRequestRef.current += 1;
    const requestId = latestRequestRef.current;
    try {
      const data = await listCvs();
      if (requestId !== latestRequestRef.current) return;
      hasListRef.current = true;
      setCvs(data);
      setError(null);
    } catch (err: unknown) {
      if (requestId !== latestRequestRef.current) return;
      if (hasListRef.current) {
        showToast(REFRESH_ERROR_MESSAGE, "error");
      } else {
        setError(err instanceof Error ? err.message : "Failed to load CVs");
      }
    } finally {
      if (requestId === latestRequestRef.current) setIsLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void fetchCvs();
    return () => {
      // Unmounted: drop any response still in flight
      latestRequestRef.current += 1;
    };
  }, [fetchCvs]);

  const handleDelete = useCallback(
    async (cv: Cv) => {
      if (!window.confirm(`Are you sure you want to delete "${cv.name}"? Applications linked to it will be unlinked. This action cannot be undone.`)) {
        return;
      }
      setDeletingId(cv.id);
      try {
        await deleteCv(cv.id);
        showToast(CV_DELETED_MESSAGE, "success");
        void fetchCvs();
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setDeletingId(null);
      }
    },
    [fetchCvs, showToast],
  );

  const handleDuplicate = useCallback(
    async (cv: Cv) => {
      setDuplicatingId(cv.id);
      try {
        await duplicateCv(cv.id);
        showToast(CV_DUPLICATED_MESSAGE, "success");
        void fetchCvs();
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setDuplicatingId(null);
      }
    },
    [fetchCvs, showToast],
  );

  const handleDownload = useCallback(
    async (cv: Cv) => {
      setDownloadingId(cv.id);
      try {
        await downloadCvTextPdf({ name: cv.name, content: cv.content });
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setDownloadingId(null);
      }
    },
    [showToast],
  );

  const handleDownloadHtml = useCallback(
    async (cv: Cv) => {
      setDownloadingHtmlId(cv.id);
      try {
        await downloadCvHtml({ name: cv.name, content: cv.content });
      } catch {
        showToast(CV_HTML_DOWNLOAD_ERROR_MESSAGE, "error");
      } finally {
        setDownloadingHtmlId(null);
      }
    },
    [showToast],
  );

  // The previous base and the copy's section change server-side: refetch
  const handleMadeBase = useCallback(() => {
    void fetchCvs();
  }, [fetchCvs]);

  const onDuplicate = useCallback((cv: Cv) => void handleDuplicate(cv), [handleDuplicate]);
  const onDownload = useCallback((cv: Cv) => void handleDownload(cv), [handleDownload]);
  const onDownloadHtml = useCallback(
    (cv: Cv) => void handleDownloadHtml(cv),
    [handleDownloadHtml],
  );
  const onDelete = useCallback((cv: Cv) => void handleDelete(cv), [handleDelete]);

  const { base, own, tailored } = useMemo(() => groupCvs(cvs), [cvs]);
  const isReady = !isLoading && !error;

  const listProps = {
    duplicatingId,
    downloadingId,
    downloadingHtmlId,
    deletingId,
    onDuplicate,
    onDownload,
    onDownloadHtml,
    onDelete,
    onMadeBase: handleMadeBase,
  };

  return (
    <PageCard maxWidth="720px">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "0.5rem",
          flexWrap: "wrap",
        }}
      >
        <PageHeader title={PAGE_TITLE} subtitle={PAGE_SUBTITLE} />
        <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
          <UploadCvButton />
          <Link to="/cvs/new" style={{ textDecoration: "none", flexShrink: 0 }}>
            <Button type="button">Create New CV</Button>
          </Link>
        </div>
      </div>

      {isLoading ? <p style={MUTED_TEXT_STYLE}>Loading...</p> : null}

      {error ? (
        <p role="alert" style={{ color: colors.error, fontSize: "0.875rem" }}>
          {error}
        </p>
      ) : null}

      {isReady && cvs.length > 0 && base === null ? (
        <p role="note" style={{ ...MUTED_TEXT_STYLE, margin: "0 0 0.5rem" }}>
          {NO_BASE_HINT}
        </p>
      ) : null}

      {isReady ? (
        <CvSection title={MY_CVS_TITLE}>
          {cvs.length === 0 ? (
            <p style={MUTED_TEXT_STYLE}>{NO_CVS_TEXT}</p>
          ) : (
            <CvList cvs={own} {...listProps} />
          )}
        </CvSection>
      ) : null}

      {isReady && tailored.length > 0 ? (
        <CvSection title={TAILORED_TITLE}>
          <CvList cvs={tailored} {...listProps} />
        </CvSection>
      ) : null}
    </PageCard>
  );
}
