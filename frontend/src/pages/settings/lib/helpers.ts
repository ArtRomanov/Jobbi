import type { User } from "@/entities/user";
import type { SettingsFormData } from "../model/schemas";

/** Convert user API data to form field values. */
export function userToFormValues(user: User): SettingsFormData {
  return {
    full_name: user.full_name,
    desired_role: user.desired_role ?? "",
    desired_location: user.desired_location ?? "",
    remote_preference: (user.remote_preference as SettingsFormData["remote_preference"]) ?? "",
    salary_min: user.salary_min !== null ? String(user.salary_min) : "",
    salary_max: user.salary_max !== null ? String(user.salary_max) : "",
    salary_currency: user.salary_currency ?? "",
    timezone: user.timezone ?? "",
    summary_time: user.summary_time,
  };
}

/** Browser's IANA timezone (e.g. "Europe/Berlin"), or null if unavailable. */
export function detectBrowserTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

// `Intl.supportedValuesOf` is ES2022; tsconfig targets ES2020 libs, so feature-detect it.
type IntlWithSupportedValues = typeof Intl & {
  supportedValuesOf?: (key: "timeZone") => string[];
};

const ETC_GMT = /^Etc\/GMT([+-])(\d{1,2})$/;

/** "Etc/GMT-4" -> "Etc/GMT-4 (UTC+4)": POSIX Etc zones invert the sign. */
function timezoneLabel(zone: string): string {
  const match = ETC_GMT.exec(zone);
  if (match) return `${zone} (UTC${match[1] === "+" ? "−" : "+"}${match[2]})`;
  return zone.replace(/_/g, " ");
}

/**
 * Options for the timezone select: every IANA zone the browser knows, plus the
 * saved and detected values. `Etc/*` zones are hidden (their inverted sign makes
 * Etc/GMT+4 mean UTC−4) unless saved or detected, and then labeled with the real
 * offset. Timezone is required for summary scheduling, so there is no "Not set"
 * choice — only a placeholder while nothing is saved yet (form validation still
 * rejects submitting it).
 */
export function getTimezoneOptions(current: string | null): Array<{ value: string; label: string }> {
  const known = (Intl as IntlWithSupportedValues).supportedValuesOf?.("timeZone") ?? [];
  const zones = new Set(known.filter((zone) => !zone.startsWith("Etc/")));
  if (current) zones.add(current);
  const detected = detectBrowserTimezone();
  if (detected) zones.add(detected);
  const options = [...zones].sort().map((zone) => ({ value: zone, label: timezoneLabel(zone) }));
  return current ? options : [{ value: "", label: "Select timezone..." }, ...options];
}
