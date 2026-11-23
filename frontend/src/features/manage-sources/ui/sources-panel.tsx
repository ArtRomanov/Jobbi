import { useCallback, useId, useRef, type ReactNode } from "react";
import { Button, SectionHeader, colors } from "@/shared/ui";
import { LOAD_ERROR_MESSAGE, NO_DESCRIPTION_HINT } from "../lib/constants";
import { pickFocusAfterRemove } from "../lib/helpers";
import type { WebSourceOptions } from "../model/schemas";
import { useAddSource } from "../model/use-add-source";
import { useManageSources } from "../model/use-manage-sources";
import type { SourcesChangeHandler } from "../model/types";
import { AddSourceForm } from "./add-source-form";
import { SearchSettingsForm } from "./search-settings-form";
import { SourcePreview } from "./source-preview";
import { SourceList } from "./source-list";
import { SourcesNotices } from "./sources-notices";

interface SourcesPanelProps {
  onScanFinished?: () => void;
  /** Live and removed sources, whenever either changes (feeds the Inbox source filter). */
  onSourcesChange?: SourcesChangeHandler;
}

/**
 * Inbox "Sources" panel: add a Telegram channel, job board or web page (with an
 * inline preview for pages), manage watched sources and
 * edit the search description + exclude words. `onScanFinished` runs when a
 * source's scan ends (the page refreshes its vacancy list).
 */
export function SourcesPanel({ onScanFinished, onSourcesChange }: SourcesPanelProps) {
  const headingId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const removeButtonsRef = useRef(new Map<string, HTMLButtonElement>());
  const {
    sources,
    settings,
    setSettings,
    status,
    loadState,
    removingIds,
    isAddDisabled,
    appendSource,
    removeSource,
    retryLoad,
  } = useManageSources(onScanFinished, onSourcesChange);
  const {
    input,
    setInput,
    addError,
    busyAction,
    isBusy,
    preview,
    previewError,
    submit,
    recheck,
    save,
    addBoard,
    cancelPreview,
  } = useAddSource(isAddDisabled, appendSource);

  const registerRemoveButton = useCallback(
    (id: string, element: HTMLButtonElement | null): void => {
      if (element) removeButtonsRef.current.set(id, element);
      else removeButtonsRef.current.delete(id);
    },
    [],
  );

  // Created or failed: back to the input. A web preview focuses its own heading.
  const handleAdd = useCallback(async (): Promise<void> => {
    const outcome = await submit();
    if (outcome === "added" || outcome === "error") inputRef.current?.focus();
  }, [submit]);

  const handleSave = useCallback(
    async (options: WebSourceOptions): Promise<boolean> => {
      const isSaved = await save(options);
      if (isSaved) inputRef.current?.focus();
      return isSaved;
    },
    [save],
  );

  const handleAddBoard = useCallback(
    async (boardInput: string): Promise<boolean> => {
      const isAdded = await addBoard(boardInput);
      if (isAdded) inputRef.current?.focus();
      return isAdded;
    },
    [addBoard],
  );

  const handleCancel = useCallback((): void => {
    cancelPreview();
    inputRef.current?.focus();
  }, [cancelPreview]);

  // After a removal, focus the next Remove button, or the input when the list is empty
  const handleRemove = useCallback(
    async (id: string): Promise<void> => {
      const orderedIds = sources.map((source) => source.id);
      const isRemoved = await removeSource(id);
      if (!isRemoved) return;
      const buttons = removeButtonsRef.current;
      const nextId = pickFocusAfterRemove(orderedIds, id, (candidate) => buttons.has(candidate));
      const target = nextId === null ? inputRef.current : buttons.get(nextId);
      target?.focus();
    },
    [sources, removeSource],
  );

  let list: ReactNode;
  switch (loadState) {
    case "loading":
      list = (
        <p role="status" style={{ fontSize: "0.875rem", color: colors.textMuted }}>
          Loading sources…
        </p>
      );
      break;
    case "error":
      list = (
        <div>
          <p role="alert" style={{ fontSize: "0.875rem", color: colors.error, marginBottom: "0.5rem" }}>
            {LOAD_ERROR_MESSAGE}
          </p>
          <Button type="button" variant="secondary" onClick={retryLoad}>
            Try again
          </Button>
        </div>
      );
      break;
    case "ready":
      list = (
        <SourceList
          sources={sources}
          removingIds={removingIds}
          onRemove={(id) => void handleRemove(id)}
          onRegisterRemoveButton={registerRemoveButton}
        />
      );
      break;
  }

  return (
    <section aria-labelledby={headingId}>
      <SectionHeader
        id={headingId}
        title="Sources"
        subtitle="Telegram channels, Greenhouse, Lever or Teamtailor boards and job pages Jobbi watches for vacancies"
      />
      {/* Based on the saved description, not the unsaved draft */}
      {settings !== null && !settings.description ? (
        <p style={{ fontSize: "0.875rem", color: colors.textSecondary, marginBottom: "1rem" }}>
          {NO_DESCRIPTION_HINT}
        </p>
      ) : null}
      <AddSourceForm
        value={input}
        error={addError}
        isBusy={isBusy}
        isAdding={busyAction === "submit"}
        isDisabled={isAddDisabled}
        inputRef={inputRef}
        onChange={setInput}
        onSubmit={() => void handleAdd()}
      />
      {preview ? (
        // A new Add re-mounts the preview: fresh fields, heading focused again
        <SourcePreview
          key={preview.id}
          result={preview.result}
          busy={isBusy}
          busyAction={busyAction === "submit" ? null : busyAction}
          error={previewError}
          onRecheck={recheck}
          onSave={handleSave}
          onCancel={handleCancel}
          onAddBoard={handleAddBoard}
        />
      ) : null}
      <SourcesNotices status={status} />
      {list}
      {/* Re-mounts once settings load so the drafts start from the saved values */}
      <SearchSettingsForm
        key={settings === null ? "loading" : "loaded"}
        initialSettings={settings}
        onSaved={setSettings}
      />
    </section>
  );
}
