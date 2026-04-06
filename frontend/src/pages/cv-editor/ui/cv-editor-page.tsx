import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createCv, getCv, updateCv, type Cv } from "@/entities/cv";
import { CvEditorForm, type CvFormValues } from "@/features/cv-editor";
import { downloadCvPdf } from "@/features/cv-pdf";
import { PageCard, PageHeader, Button, colors, useToast } from "@/shared/ui";
import { handleApiError } from "@/shared/api";

/**
 * Page that wraps CvEditorForm for both create and edit modes.
 * Create: /cvs/new — empty form, POST on save, redirect to /cvs.
 * Edit: /cvs/:id/edit — fetches CV, pre-fills form, PATCH on save.
 */
export function CvEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const isEditMode = Boolean(id);

  const [cv, setCv] = useState<Cv | null>(null);
  const [isLoading, setIsLoading] = useState(isEditMode);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    getCv(id)
      .then((data) => {
        if (!cancelled) {
          setCv(data);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load CV",
          );
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleSave = useCallback(
    async (values: CvFormValues): Promise<void> => {
      setIsSaving(true);
      try {
        const payload = {
          name: values.name,
          personal_info: values.personal_info,
          summary: values.summary || null,
          work_experience:
            values.work_experience.length > 0
              ? values.work_experience
              : null,
          education:
            values.education.length > 0 ? values.education : null,
          skills: values.skills || null,
          languages: values.languages || null,
        };

        if (id) {
          await updateCv(id, payload);
          showToast("CV updated.", "success");
        } else {
          await createCv({ ...payload, name: values.name });
          showToast("CV created.", "success");
        }
        navigate("/cvs");
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setIsSaving(false);
      }
    },
    [id, navigate, showToast],
  );

  const handleDownload = useCallback(async () => {
    if (!cv) return;
    try {
      await downloadCvPdf(cv);
    } catch (err: unknown) {
      handleApiError(err, showToast);
    }
  }, [cv, showToast]);

  return (
    <PageCard maxWidth="640px">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <PageHeader
          title={isEditMode ? "Edit CV" : "Create New CV"}
          subtitle={
            isEditMode
              ? "Update your CV details below."
              : "Fill in the sections to build your CV."
          }
        />
        {isEditMode && cv && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => void handleDownload()}
          >
            Download PDF
          </Button>
        )}
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

      {!isLoading && !error && (
        <CvEditorForm
          initialData={cv ?? undefined}
          onSave={handleSave}
          isSaving={isSaving}
        />
      )}
    </PageCard>
  );
}
