import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createCv, getCv, updateCv, type Cv } from "@/entities/cv";
import {
  CvTextEditor,
  getCvSaveErrorMessage,
  type CvTextEditorValues,
} from "@/features/cv-text-editor";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { UploadNotice } from "@/features/cv-upload";
import { PageCard, PageHeader, colors, useToast } from "@/shared/ui";
import { handleApiError } from "@/shared/api";

interface EditorSeed {
  key: string;
  values: CvTextEditorValues;
}

const EMPTY_VALUES: CvTextEditorValues = { name: "", content: "" };

function toEditorSeed(cv: Cv | null, newKey: string): EditorSeed {
  return cv
    ? { key: cv.id, values: { name: cv.name, content: cv.content } }
    : { key: newKey, values: { name: "", content: "" } };
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
  // The last saved (or loaded) CV; its `version` goes with the next PATCH.
  // State drives rendering; the ref is what the effect and the handlers read,
  // so neither re-runs on save. Both change only through `setSavedCv`.
  const [cv, setCv] = useState<Cv | null>(null);
  const cvRef = useRef<Cv | null>(null);
  const setSavedCv = useCallback((next: Cv | null) => {
    cvRef.current = next;
    setCv(next);
  }, []);
  // What the editor is mounted with. Changes only when a different CV loads
  // (or a fresh /cvs/new starts), never on save, so saving keeps the editor
  // and the user's draft as they are.
  const [editorSeed, setEditorSeed] = useState(() => toEditorSeed(null, "new-0"));
  const newEditorCountRef = useRef(0);
  const [isLoading, setIsLoading] = useState(isEditMode);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  // Shown next to Save until the next attempt; the draft stays in the editor
  const [saveError, setSaveError] = useState<string | null>(null);
  // Blocks a second save until the first settles (`isSaving` lags a render)
  const isSavingRef = useRef(false);

  useEffect(() => {
    setSaveError(null);
    if (!id) {
      // Same page instance moved to /cvs/new: start a fresh CV
      setError(null);
      setIsLoading(false);
      if (cvRef.current) {
        setSavedCv(null);
        newEditorCountRef.current += 1;
        setEditorSeed(toEditorSeed(null, `new-${newEditorCountRef.current}`));
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
        setSavedCv(data);
        setEditorSeed(toEditorSeed(data, ""));
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
  }, [id, setSavedCv]);

  const handleSave = useCallback(
    async (values: CvTextEditorValues): Promise<void> => {
      if (isSavingRef.current) return;
      isSavingRef.current = true;
      setIsSaving(true);
      setSaveError(null);
      try {
        const current = cvRef.current;
        if (current) {
          const saved = await updateCv(current.id, { ...values, version: current.version });
          setSavedCv(saved);
          showToast("CV saved", "success");
        } else {
          const created = await createCv(values);
          // Set before navigating so the load effect for the new id is skipped
          setSavedCv(created);
          showToast("CV saved", "success");
          // The router keeps this page (and the editor) mounted across the
          // /cvs/new → /cvs/:id/edit move, so the draft and focus stay put
          navigate(`/cvs/${created.id}/edit`, { replace: true });
        }
      } catch (err: unknown) {
        // A 409 (changed elsewhere) must not overwrite: the draft stays as typed
        setSaveError(getCvSaveErrorMessage(err));
      } finally {
        isSavingRef.current = false;
        setIsSaving(false);
      }
    },
    [navigate, setSavedCv, showToast],
  );

  // What "Save" and the unsaved-changes guard compare the draft with
  const savedValues = useMemo<CvTextEditorValues>(
    () => (cv ? { name: cv.name, content: cv.content } : EMPTY_VALUES),
    [cv],
  );

  // Exports what the user sees in the editor, saved or not
  const handleExport = useCallback(
    async (values: CvTextEditorValues): Promise<void> => {
      try {
        await downloadCvTextPdf(values);
      } catch (err: unknown) {
        handleApiError(err, showToast);
      }
    },
    [showToast],
  );

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
      <PageHeader
        title={isEditMode ? "Edit CV" : "Create New CV"}
        subtitle="Write your CV as text; the preview shows how it will look."
      />

      {/* Only after an upload (router state); shown once */}
      <UploadNotice />

      {isLoading && (
        <p style={{ color: colors.textMuted, fontSize: "0.875rem" }}>Loading...</p>
      )}

      {error && <p style={{ color: colors.error, fontSize: "0.875rem" }}>{error}</p>}

      {!isLoading && !error && (
        <CvTextEditor
          key={editorSeed.key}
          initialValues={editorSeed.values}
          savedValues={savedValues}
          onSave={handleSave}
          isSaving={isSaving}
          saveError={saveError}
          onExport={isEditMode && cv ? handleExport : undefined}
        />
      )}
    </PageCard>
  );
}
