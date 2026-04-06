import type { components } from "@/shared/api";

/** Re-export the generated ChatMessageRead schema as the domain type. */
export type ChatMessage = components["schemas"]["ChatMessageRead"];
