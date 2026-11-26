import type {
  DiscoveryStatus,
  RemovedVacancySource,
  VacancySearchSettings,
  VacancySource,
  VacancySourcePreview,
} from "@/entities/vacancy-source";
import type { EditSourceValues, WebSourceOptions } from "./schemas";

/** Inline validation messages of the web source preview fields. */
export type WebSourceFieldErrors = Partial<Record<keyof WebSourceOptions, string>>;

export type SourcesLoadState = "loading" | "error" | "ready";

/** Live sources + sources that only existing cards still reference. */
export type SourcesChangeHandler = (
  sources: readonly VacancySource[],
  removedSources: readonly RemovedVacancySource[],
) => void;

/** Sends a removal's DELETE and applies the result; never rejects. */
export type SendRemove = (id: string, options: { keepalive: boolean }) => Promise<void>;

export interface UseDeferredRemoveResult {
  /** Rows hidden by a removal that is waiting for its Undo window or its DELETE. */
  pendingIds: ReadonlySet<string>;
  /** Hide the row and open its Undo toast; `onUndo` runs after Undo shows it again. */
  scheduleRemove: (id: string, onUndo?: () => void) => void;
  /** Send every pending removal now (closes their toasts); resolves when all settled. */
  flushRemovals: () => Promise<void>;
}

export interface UseManageSourcesResult {
  /** Sources to show: rows whose removal is pending (Undo window / DELETE in flight) are left out. */
  sources: readonly VacancySource[];
  /** Saved search settings; null until the initial load succeeds. */
  settings: VacancySearchSettings | null;
  /** Replace the saved settings (e.g. with the server-normalized values after a save). */
  setSettings: (settings: VacancySearchSettings) => void;
  /** Daily limit / AI availability; null until the initial load succeeds. */
  status: DiscoveryStatus | null;
  loadState: SourcesLoadState;
  /** True until the initial list has loaded; adding is blocked meanwhile. */
  isAddDisabled: boolean;
  /** Append a just-created source to the local list. */
  appendSource: (source: VacancySource) => void;
  /**
   * Put the server's copy in place of `previousId` after an edit. A different
   * id means the source was replaced: the removed list is re-fetched too.
   */
  replaceSource: (previousId: string, source: VacancySource) => void;
  /**
   * Hide the source with an Undo toast; the DELETE goes when the toast ends.
   * `onUndo` runs after Undo puts the row back (e.g. to focus it).
   */
  removeSource: (id: string, onUndo?: () => void) => void;
  /** Send pending removals now (e.g. before an add, so the server sees them gone). */
  flushRemovals: () => Promise<void>;
  retryLoad: () => void;
}

/** A finished Remove waiting for its focus target (picked after the list updates). */
export interface RemoveFocusRequest {
  /** Full-list order when Remove was pressed. */
  orderedIds: readonly string[];
  removedId: string;
}

export interface UseSourcePagesResult {
  /** Current page (0-based), always valid for the list. */
  page: number;
  pageCount: number;
  /** The sources shown on the current page. */
  pageSources: readonly VacancySource[];
  /** Go to a page (clamped). */
  setPage: (page: number) => void;
  /** Open the page that shows this source once it is in the list (e.g. right after adding it). */
  revealSource: (id: string) => void;
}

export interface UseSearchSettingsFormResult {
  description: string;
  setDescription: (value: string) => void;
  /** Keyword drafts (chips); the server lowercases / de-dupes them on save. */
  keywords: readonly string[];
  setKeywords: (value: readonly string[]) => void;
  /** "Only send posts with these words to the AI" draft. */
  keywordFilter: boolean;
  setKeywordFilter: (value: boolean) => void;
  /** Drafts differ from the saved settings after server-style normalization (false until loaded). */
  isDirty: boolean;
  /** Inline error under the Save button, or null. */
  saveError: string | null;
  isSaving: boolean;
  /** Save description + keywords + switch in one PATCH; resolves true on success. */
  save: () => Promise<boolean>;
}

/** Which add-flow request is running ("board": adding the ATS board a preview hints at). */
export type AddSourceAction = "submit" | "recheck" | "save" | "board";

/** What Add did: created a source, opened a web preview, failed, or did nothing. */
export type AddSubmitOutcome = "added" | "preview" | "error" | "skipped";

/** An open web page preview. `id` changes on every new Add (the form re-mounts). */
export interface WebPreview {
  id: number;
  /** The trimmed input the preview was made for (Save sends this, not the live input). */
  input: string;
  result: VacancySourcePreview;
}

export interface UseAddSourceResult {
  input: string;
  setInput: (value: string) => void;
  /** Inline error under the add input, or null. */
  addError: string | null;
  busyAction: AddSourceAction | null;
  isBusy: boolean;
  preview: WebPreview | null;
  /** Re-check / save error shown inside the preview, or null. */
  previewError: string | null;
  submit: () => Promise<AddSubmitOutcome>;
  recheck: (jobLinkContains: string | null) => Promise<void>;
  /** Resolves true when the web source was created. */
  save: (options: WebSourceOptions) => Promise<boolean>;
  /** Adds the hinted board like a pasted board link; resolves true when created. */
  addBoard: (boardInput: string) => Promise<boolean>;
  cancelPreview: () => void;
}

/** Which Edit-dialog request is running ("check": Save on the form, previewing a changed link). */
export type EditSourceAction = "check" | "recheck" | "save";

/** Edit-form field focused after a failed submit. */
export type EditSourceField = "name" | "link";

/** A web preview inside the Edit dialog, with the drafts it starts from. */
export interface EditPreview extends WebPreview {
  initialJobLinkContains: string;
  initialName: string;
}

export interface UseEditSourceResult {
  busyAction: EditSourceAction | null;
  isBusy: boolean;
  /** Inline error above the form buttons, or null. */
  error: string | null;
  /** Open web preview (a changed link / pattern that is a web page), or null. */
  preview: EditPreview | null;
  /** Re-check / save error shown inside the preview, or null. */
  previewError: string | null;
  /** Form Save: name-only → PATCH; changed link / pattern → preview first. */
  /** Resolves with the field to focus when the request failed, else null. */
  submit: (values: EditSourceValues) => Promise<EditSourceField | null>;
  recheck: (jobLinkContains: string | null) => Promise<void>;
  /** Preview Save; resolves true when saved. */
  savePreview: (options: WebSourceOptions) => Promise<boolean>;
  /** Back from the preview to the form (no-op while a request runs). */
  closePreview: () => void;
}

/** Called with the server's copy after a successful edit (a replace has a new id). */
export type SourceEditedHandler = (source: VacancySource) => void;

/** Edit success inside the panel: the edited row's id and the server's copy. */
export type SourceSavedHandler = (previousId: string, source: VacancySource) => void;
