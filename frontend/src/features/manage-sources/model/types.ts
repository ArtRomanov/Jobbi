import type {
  DiscoveryStatus,
  RemovedVacancySource,
  VacancySearchSettings,
  VacancySource,
} from "@/entities/vacancy-source";

export type SourcesLoadState = "loading" | "error" | "ready";

/** Live sources + sources that only existing cards still reference. */
export type SourcesChangeHandler = (
  sources: readonly VacancySource[],
  removedSources: readonly RemovedVacancySource[],
) => void;

export interface UseManageSourcesResult {
  sources: readonly VacancySource[];
  /** Saved search settings; null until the initial load succeeds. */
  settings: VacancySearchSettings | null;
  /** Replace the saved settings (e.g. with the server-normalized values after a save). */
  setSettings: (settings: VacancySearchSettings) => void;
  /** Daily limit / AI availability; null until the initial load succeeds. */
  status: DiscoveryStatus | null;
  loadState: SourcesLoadState;
  input: string;
  setInput: (value: string) => void;
  /** Inline error under the add input, or null. */
  addError: string | null;
  isAdding: boolean;
  /** Ids of sources with a delete request in flight. */
  removingIds: ReadonlySet<string>;
  /** True until the initial list has loaded; adding is blocked meanwhile. */
  isAddDisabled: boolean;
  addSource: () => Promise<void>;
  /** Resolves true when the source was removed. */
  removeSource: (id: string) => Promise<boolean>;
  retryLoad: () => void;
}

export interface UseSearchSettingsFormResult {
  description: string;
  setDescription: (value: string) => void;
  /** Inline error under the Save button, or null. */
  saveError: string | null;
  isSaving: boolean;
  /** Save the description (exclude words are not sent); resolves true on success. */
  save: () => Promise<boolean>;
}
