import type { VacancySource } from "@/entities/vacancy-source";

export type SourcesLoadState = "loading" | "error" | "ready";

export interface UseManageSourcesResult {
  sources: readonly VacancySource[];
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
