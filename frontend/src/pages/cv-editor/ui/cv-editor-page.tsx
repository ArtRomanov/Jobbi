import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { createCv, CvTailoredFor, getCv, isTailoredCv, updateCv, type Cv } from "@/entities/cv";
import {
  CvTextEditor,
  getCvSaveErrorMessage,
  type CvTextEditorValues,
  type CvTextExportValues,
} from "@/features/cv-text-editor";
import { downloadCvTextPdf } from "@/features/cv-pdf";
import { UploadNotice, useUploadDraft, type UploadDraft } from "@/features/cv-upload";
import { Badge, PageCard, PageHeader, colors, useToast } from "@/shared/ui";
import { handleApiError } from "@/shared/api";
import {
  BASE_LABEL,
  CV_SAVED_AS_BASE_MESSAGE,
  CV_SAVED_MESSAGE,
  CV_SAVED_NO_BASE_MESSAGE,
  TAILORED_FOR_PREFIX,
} from "../lib/constants";

interface EditorSeed {
  key: string;
  values: CvTextEditorValues;
}

const EMPTY_VALUES: CvTextEditorValues = { name: "", content: "", isBase: false };
/** Editor key of the first new CV this page mounts (the only one an upload draft seeds). */
const FIRST_NEW_KEY = "new-0";

function toEditorValues(cv: Cv): CvTextEditorValues {
  return { name: cv.name, content: cv.content, isBase: cv.is_base };
}

/**
 * A loaded CV starts from its saved values; a new CV from the upload draft
 * (if any; its switch starts off, spec 2.3) or empty.
 */
function toEditorSeed(cv: Cv | null, newKey: string, draft: UploadDraft | null = null): EditorSeed {
  if (cv) return { key: cv.id, values: toEditorValues(cv) };
  if (draft) {
    return { key: newKey, values: { name: draft.name, content: draft.content, isBase: false } };
  }
  return { key: newKey, values: EMPTY_VALUES };
}

/** The save toast: says when the switch made the CV the base or removed it. */
function getSavedMessage(wasBase: boolean, saved: Cv): string {
  if (saved.is_base && !wasBase) return CV_SAVED_AS_BASE_MESSAGE;
  if (!saved.is_base && wasBase) return CV_SAVED_NO_BASE_MESSAGE;
  return CV_SAVED_MESSAGE;
}

/**
 * Composes `CvTextEditor` for both routes.
 * /cvs/new — empty editor, or the upload draft from router state (unsaved
 * until Save; "Leave" drops it); Save creates the CV and moves to its edit URL.
 * /cvs/:id/edit — loads the CV; Save PATCHes with the loaded `version` and
 * keeps the returned one for the next save.
 */
export function CvEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const isEditMode = Boolean(id);
  // Only on /cvs/new right after an upload; a reload opens an empty new CV
  const uploadDraft = useUploadDraft();
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
  const [editorSeed, setEditorSeed] = useState(() =>
    toEditorSeed(null, FIRST_NEW_KEY, isEditMode ? null : uploadDraft),
  );
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
          const saved = await updateCv(current.id, {
            name: values.name,
            content: values.content,
            version: current.version,
            // Only when the switch changed: never clear a base set elsewhere
            ...(values.isBase !== current.is_base ? { is_base: values.isBase } : {}),
          });
          setSavedCv(saved);
          showToast(getSavedMessage(current.is_base, saved), "success");
        } else {
          const created = await createCv({
            name: values.name,
            content: values.content,
            is_base: values.isBase,
          });
          // Set before navigating so the load effect for the new id is skipped
          setSavedCv(created);
          showToast(getSavedMessage(false, created), "success");
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
    () => (cv ? toEditorValues(cv) : EMPTY_VALUES),
    [cv],
  );

  // Exports what the user sees in the editor, saved or not
  const handleExport = useCallback(
    async (values: CvTextExportValues): Promise<void> => {
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

      {/* Base label / the application a tailored copy was made for (spec 011 §2.1) */}
      {cv && (cv.is_base || isTailoredCv(cv)) ? (
        <p
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            flexWrap: "wrap",
            margin: "-1rem 0 1rem",
            fontSize: "0.875rem",
            color: colors.textSecondary,
          }}
        >
          {cv.is_base ? <Badge tone="accent">{BASE_LABEL}</Badge> : null}
          {isTailoredCv(cv) ? (
            <span>
              {TAILORED_FOR_PREFIX} <CvTailoredFor cv={cv} />
            </span>
          ) : null}
        </p>
      ) : null}

      {/* An uploaded draft not saved yet (spec 2.3) */}
      {uploadDraft && !cv && editorSeed.key === FIRST_NEW_KEY ? (
        <UploadNotice truncated={uploadDraft.truncated} />
      ) : null}

      {isLoading && (
        <p style={{ color: colors.textMuted, fontSize: "0.875rem" }}>Loading...</p>
      )}

      {error && (
        <p role="alert" style={{ color: colors.error, fontSize: "0.875rem" }}>
          {error}
        </p>
      )}

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
