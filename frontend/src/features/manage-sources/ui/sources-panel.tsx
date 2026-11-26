import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { VacancySource } from "@/entities/vacancy-source";
import { useCollapsibleSection } from "@/shared/lib";
import { Button, SectionHeader, SectionToggle, colors } from "@/shared/ui";
import { LOAD_ERROR_MESSAGE, NO_DESCRIPTION_HINT, SOURCES_COLLAPSED_STORAGE_KEY } from "../lib/constants";
import { pickFocusAfterRemove } from "../lib/helpers";
import type { WebSourceOptions } from "../model/schemas";
import { useAddSource } from "../model/use-add-source";
import { useManageSources } from "../model/use-manage-sources";
import { useSourcePages } from "../model/use-source-pages";
import type { SourceEditedHandler, SourcesChangeHandler } from "../model/types";
import { AddSourceForm } from "./add-source-form";
import { SearchSettingsForm } from "./search-settings-form";
import { SourcePreview } from "./source-preview";
import { SourceList } from "./source-list";
import { SourcesPager } from "./sources-pager";
import { SourcesNotices } from "./sources-notices";

interface SourcesPanelProps {
  onScanFinished?: () => void;
  /** Live and removed sources, whenever either changes (feeds the Inbox source filter). */
  onSourcesChange?: SourcesChangeHandler;
  /** After a successful edit (the page refreshes its vacancy list so cards show the new name). */
  onSourceEdited?: SourceEditedHandler;
}

/**
 * Inbox "Sources" panel: add a Telegram channel, job board or web page (with an
 * inline preview for pages), manage watched sources and
 * edit the search description. `onScanFinished` runs when a
 * source's scan ends (the page refreshes its vacancy list).
 */
export function SourcesPanel({ onScanFinished, onSourcesChange, onSourceEdited }: SourcesPanelProps) {
  const headingId = useId();
  const collapsible = useCollapsibleSection(SOURCES_COLLAPSED_STORAGE_KEY);
  const inputRef = useRef<HTMLInputElement>(null);
  const removeButtonsRef = useRef(new Map<string, HTMLButtonElement>());
  const editButtonsRef = useRef(new Map<string, HTMLButtonElement>());
  // A replaced source gets a new row, so the Modal can't return focus to its Edit
  const [focusEditId, setFocusEditId] = useState<string | null>(null);
  // Remove emptied its page: the clamp shows the previous page, focus lands after render
  const [focusRemoveId, setFocusRemoveId] = useState<string | null>(null);
  const {
    sources,
    settings,
    setSettings,
    status,
    loadState,
    removingIds,
    isAddDisabled,
    appendSource,
    replaceSource,
    removeSource,
    retryLoad,
  } = useManageSources(onScanFinished, onSourcesChange);
  // Paging is view-only: `onSourcesChange` above still gets the FULL list
  const { page, pageCount, pageSources, setPage, revealSource } = useSourcePages(sources);
  // A new source is appended at the end: open the page that shows it
  const appendAndReveal = useCallback(
    (source: VacancySource): void => {
      appendSource(source);
      revealSource(source.id);
    },
    [appendSource, revealSource],
  );
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
  } = useAddSource(isAddDisabled, appendAndReveal);

  const registerRemoveButton = useCallback(
    (id: string, element: HTMLButtonElement | null): void => {
      if (element) removeButtonsRef.current.set(id, element);
      else removeButtonsRef.current.delete(id);
    },
    [],
  );

  const registerEditButton = useCallback(
    (id: string, element: HTMLButtonElement | null): void => {
      if (element) editButtonsRef.current.set(id, element);
      else editButtonsRef.current.delete(id);
    },
    [],
  );

  // Passive effect: runs after the dialog's unmount cleanup, so nothing steals focus after it
  useEffect(() => {
    if (focusEditId === null) return;
    // Edit stays focusable while a first scan blocks it (aria-disabled + reason)
    const target = editButtonsRef.current.get(focusEditId) ?? removeButtonsRef.current.get(focusEditId);
    target?.focus();
    setFocusEditId(null);
  }, [focusEditId]);

  useEffect(() => {
    if (focusRemoveId === null) return;
    // Gone meanwhile (e.g. removed concurrently): fall back to the input
    (removeButtonsRef.current.get(focusRemoveId) ?? inputRef.current)?.focus();
    setFocusRemoveId(null);
  }, [focusRemoveId]);

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

  const handleEdited = useCallback(
    (previousId: string, source: VacancySource): void => {
      replaceSource(previousId, source);
      if (source.id !== previousId) setFocusEditId(source.id);
      onSourceEdited?.(source);
    },
    [replaceSource, onSourceEdited],
  );

  // After a removal, focus the next Remove button on the page, else the previous
  // one; a page left empty shows the previous page (clamp) and focuses its last
  // Remove; the input when the list is empty
  const handleRemove = useCallback(
    async (id: string): Promise<void> => {
      const orderedIds = pageSources.map((source) => source.id);
      const allIds = sources.map((source) => source.id);
      const isRemoved = await removeSource(id);
      if (!isRemoved) return;
      const buttons = removeButtonsRef.current;
      const nextId = pickFocusAfterRemove(orderedIds, id, (candidate) => buttons.has(candidate));
      if (nextId !== null) {
        buttons.get(nextId)?.focus();
        return;
      }
      const otherPageId = pickFocusAfterRemove(allIds, id, () => true);
      if (otherPageId === null) inputRef.current?.focus();
      else setFocusRemoveId(otherPageId);
    },
    [pageSources, sources, removeSource],
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
        <>
          <SourceList
            sources={pageSources}
            removingIds={removingIds}
            onRemove={(id) => void handleRemove(id)}
            onEdited={handleEdited}
            onRegisterRemoveButton={registerRemoveButton}
            onRegisterEditButton={registerEditButton}
          />
          <SourcesPager page={page} pageCount={pageCount} onPageChange={setPage} />
        </>
      );
      break;
  }

  return (
    <section aria-labelledby={headingId}>
      <SectionHeader
        id={headingId}
        title="Sources"
        subtitle="Telegram channels, Greenhouse, Lever, Teamtailor or Ashby boards and job pages Jobbi watches for vacancies"
        action={
          <SectionToggle
            label="Sources"
            isExpanded={collapsible.isExpanded}
            controlsId={collapsible.regionId}
            onToggle={collapsible.toggle}
          />
        }
      />
      {/* `hidden`, not unmount: drafts, open preview and polling (feeds the Inbox filter) go on */}
      <div id={collapsible.regionId} hidden={!collapsible.isExpanded}>
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
          filteredLast24h={status?.filtered_last_24h ?? null}
        />
      </div>
    </section>
  );
}
