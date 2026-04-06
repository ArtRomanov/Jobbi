import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listCvs, deleteCv, duplicateCv, type Cv } from "@/entities/cv";
import { downloadCvPdf } from "@/features/cv-pdf";
import { PageCard, PageHeader, Button, colors } from "@/shared/ui";
import { handleApiError } from "@/shared/api";
import { useToast } from "@/shared/ui";

/**
 * CV list page showing all user CVs with actions for edit, duplicate,
 * download PDF, and delete. Lives in `pages/` because it is a route.
 */
export function CvsPage() {
  const [cvs, setCvs] = useState<Cv[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);
  const { showToast } = useToast();

  const fetchCvs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listCvs();
      setCvs(data);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to load CVs",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchCvs();
  }, [fetchCvs]);

  const handleDelete = useCallback(
    async (cv: Cv) => {
      if (!window.confirm(`Are you sure you want to delete "${cv.name}"? Applications linked to it will be unlinked. This action cannot be undone.`)) {
        return;
      }
      setDeletingId(cv.id);
      try {
        await deleteCv(cv.id);
        showToast("CV deleted.", "success");
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
        showToast("CV duplicated.", "success");
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
        await downloadCvPdf(cv);
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setDownloadingId(null);
      }
    },
    [showToast],
  );

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  return (
    <PageCard maxWidth="720px">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <PageHeader
          title="My CVs"
          subtitle="Manage your resumes and download as PDF."
        />
        <Link
          to="/cvs/new"
          style={{ textDecoration: "none", flexShrink: 0 }}
        >
          <Button type="button">Create New CV</Button>
        </Link>
      </div>

      {isLoading && (
        <p style={{ color: colors.textMuted, fontSize: "0.875rem" }}>
          Loading...
        </p>
      )}

      {error && (
        <p style={{ color: colors.error, fontSize: "0.875rem" }}>
          {error}
        </p>
      )}

      {!isLoading && !error && cvs.length === 0 && (
        <p style={{ color: colors.textMuted, fontSize: "0.875rem" }}>
          No CVs yet. Create your first one to get started.
        </p>
      )}

      {!isLoading && !error && cvs.length > 0 && (
        <div>
          {cvs.map((cv) => (
            <div
              key={cv.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.75rem 0",
                borderBottom: `1px solid ${colors.borderLight}`,
              }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
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
                </div>
                <div
                  style={{
                    fontSize: "0.75rem",
                    color: colors.textMuted,
                    marginTop: "0.125rem",
                  }}
                >
                  Updated {formatDate(cv.updated_at)}
                  {cv.linked_applications_count > 0 && (
                    <span>
                      {" \u00B7 "}
                      {cv.linked_applications_count} application
                      {cv.linked_applications_count !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "0.5rem",
                  flexShrink: 0,
                  marginLeft: "1rem",
                }}
              >
                <Link
                  to={`/cvs/${cv.id}/edit`}
                  style={{ textDecoration: "none" }}
                >
                  <Button type="button" variant="secondary">
                    Edit
                  </Button>
                </Link>
                <Button
                  type="button"
                  variant="secondary"
                  loading={duplicatingId === cv.id}
                  onClick={() => void handleDuplicate(cv)}
                >
                  Duplicate
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  loading={downloadingId === cv.id}
                  onClick={() => void handleDownload(cv)}
                >
                  PDF
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  style={{ color: colors.error, borderColor: colors.error }}
                  loading={deletingId === cv.id}
                  onClick={() => void handleDelete(cv)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </PageCard>
  );
}
