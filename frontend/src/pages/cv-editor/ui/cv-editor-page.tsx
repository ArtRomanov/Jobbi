import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createCv, getCv, updateCv, type Cv } from "@/entities/cv";
import { CvTextEditor, type CvTextEditorValues } from "@/features/cv-text-editor";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { PageCard, PageHeader, Button, colors, useToast } from "@/shared/ui";
import { handleApiError } from "@/shared/api";

interface EditorSeed {
  key: string;
  values: CvTextEditorValues;
}

let newEditorCount = 0;

function toEditorSeed(cv: Cv | null): EditorSeed {
  if (cv) return { key: cv.id, values: { name: cv.name, content: cv.content } };
  newEditorCount += 1;
  return { key: `new-${newEditorCount}`, values: { name: "", content: "" } };
}

/**
 * Composes `CvTextEditor` for both routes.
 * /cvs/new — empty editor; Save creates the CV and moves to its edit URL.
 * /cvs/:id/edit — loads the CV; Save PATCHes with the loaded `version` and
 * keeps the returned one for the next save.
 */
export function CvEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const isEditMode = Boolean(id);
  // The last saved (or loaded) CV; its `version` goes with the next PATCH
  const [cv, setCv] = useState<Cv | null>(null);
  // What the editor is mounted with. Changes only when a different CV loads,
  // never on save, so saving keeps the editor (and the user's draft) as is.
  const [editorSeed, setEditorSeed] = useState(() => toEditorSeed(null));
  const [isLoading, setIsLoading] = useState(isEditMode);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Read in the effect and the save handler, so neither re-runs on save
  const cvRef = useRef(cv);
  cvRef.current = cv;

  useEffect(() => {
    if (!id) {
      // Same page instance moved to /cvs/new: start a fresh CV
      if (cvRef.current) {
        cvRef.current = null;
        setCv(null);
        setEditorSeed(toEditorSeed(null));
      }
      return;
    }
    if (cvRef.current?.id === id) return;

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    getCv(id)
      .then((data) => {
        if (cancelled) return;
        setCv(data);
        setEditorSeed(toEditorSeed(data));
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load CV");
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleSave = useCallback(
    async (values: CvTextEditorValues): Promise<void> => {
      setIsSaving(true);
      try {
        const current = cvRef.current;
        if (current) {
          const saved = await updateCv(current.id, { ...values, version: current.version });
          setCv(saved);
          showToast("CV saved", "success");
        } else {
          const created = await createCv(values);
          // Set before navigating so the load effect for the new id is skipped
          cvRef.current = created;
          setCv(created);
          showToast("CV saved", "success");
          // The router keeps this page (and the editor) mounted across the
          // /cvs/new → /cvs/:id/edit move, so the draft and focus stay put
          navigate(`/cvs/${created.id}/edit`, { replace: true });
        }
      } catch (err: unknown) {
        handleApiError(err, showToast);
      } finally {
        setIsSaving(false);
      }
    },
    [navigate, showToast],
  );

  const handleExport = useCallback(async () => {
    if (!cv) return;
    try {
      await downloadCvTextPdf({ name: cv.name, content: cv.content });
    } catch (err: unknown) {
      handleApiError(err, showToast);
    }
  }, [cv, showToast]);


  return (
    <PageCard maxWidth="1120px">
      <Link
        to="/cvs"
        style={{
          fontSize: "0.875rem",
          color: colors.primary,
          textDecoration: "none",
          display: "inline-block",
          marginBottom: "1rem",
        }}
      >
        ← Back to CVs
      </Link>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <PageHeader
          title={isEditMode ? "Edit CV" : "Create New CV"}
          subtitle="Write your CV as text; the preview shows how it will look."
        />
        {isEditMode && cv && (
          <Button type="button" variant="secondary" onClick={() => void handleExport()}>
            Export PDF
          </Button>
        )}
      </div>

      {isLoading && (
        <p style={{ color: colors.textMuted, fontSize: "0.875rem" }}>Loading...</p>
      )}

      {error && <p style={{ color: colors.error, fontSize: "0.875rem" }}>{error}</p>}

      {!isLoading && !error && (
        <CvTextEditor
          key={editorSeed.key}
          initialValues={editorSeed.values}
          onSave={handleSave}
          isSaving={isSaving}
        />
      )}
    </PageCard>
  );
}
