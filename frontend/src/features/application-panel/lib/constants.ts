import { STATUSES } from "@/entities/application";

export const STATUS_OPTIONS = STATUSES.map((s) => ({ value: s.key, label: s.label }));
