import { Button } from "./button";
import { VisuallyHidden } from "./visually-hidden";

interface SectionToggleProps {
  /** Section name, read after the visible "Hide" / "Show" ("Hide Sources"). */
  label: string;
  isExpanded: boolean;
  /** Id of the region it shows and hides. */
  controlsId: string;
  onToggle: () => void;
}

/** Disclosure button for a collapsible section (`aria-expanded` + `aria-controls`). */
export function SectionToggle({ label, isExpanded, controlsId, onToggle }: SectionToggleProps) {
  return (
    <Button
      type="button"
      variant="secondary"
      aria-expanded={isExpanded}
      aria-controls={controlsId}
      onClick={onToggle}
      style={{ padding: "0.25rem 0.75rem", flexShrink: 0 }}
    >
      {isExpanded ? "Hide" : "Show"}
      <VisuallyHidden> {label}</VisuallyHidden>
    </Button>
  );
}
