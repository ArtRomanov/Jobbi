import { useCallback, useId, useRef, type ReactNode } from "react";
import { Button, SectionHeader, colors } from "@/shared/ui";
import { LOAD_ERROR_MESSAGE } from "../lib/constants";
import { pickFocusAfterRemove } from "../lib/helpers";
import { useManageSources } from "../model/use-manage-sources";
import { AddSourceForm } from "./add-source-form";
import { SourceList } from "./source-list";

/** Inbox "Sources" panel: add a Telegram channel and manage watched sources. */
export function SourcesPanel() {
  const headingId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const removeButtonsRef = useRef(new Map<string, HTMLButtonElement>());
  const {
    sources,
    loadState,
    input,
    setInput,
    addError,
    isAdding,
    removingIds,
    isAddDisabled,
    addSource,
    removeSource,
    retryLoad,
  } = useManageSources();

  const registerRemoveButton = useCallback(
    (id: string, element: HTMLButtonElement | null): void => {
      if (element) removeButtonsRef.current.set(id, element);
      else removeButtonsRef.current.delete(id);
    },
    [],
  );

  // Success or failure, return focus to the input so the user can type again
  const handleAdd = useCallback(async (): Promise<void> => {
    await addSource();
    inputRef.current?.focus();
  }, [addSource]);

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
        subtitle="Telegram channels Jobbi watches for vacancies"
      />
      <AddSourceForm
        value={input}
        error={addError}
        isAdding={isAdding}
        isDisabled={isAddDisabled}
        inputRef={inputRef}
        onChange={setInput}
        onSubmit={() => void handleAdd()}
      />
      {list}
    </section>
  );
}
