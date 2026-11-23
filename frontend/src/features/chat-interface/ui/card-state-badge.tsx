import type { ChangeCardState } from "@/entities/chat";
import { Badge } from "@/shared/ui";

/** "Accepted" (with a check), "Rejected" or "Stale"; nothing while pending. */
export function CardStateBadge({ state }: { state: ChangeCardState }) {
  switch (state) {
    case "accepted":
      return (
        <Badge tone="success">
          <span aria-hidden="true" style={{ marginRight: "0.25rem" }}>
            ✓
          </span>
          Accepted
        </Badge>
      );
    case "rejected":
      return <Badge tone="neutral">Rejected</Badge>;
    case "stale":
      return <Badge tone="warning">Stale</Badge>;
    case "pending":
      return null;
  }
}
