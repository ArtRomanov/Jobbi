import { afterEach, describe, expect, it, vi } from "vitest";
import { getTimezoneOptions } from "@/pages/settings/lib/helpers";

const ZONES = ["Asia/Dubai", "Etc/GMT+4", "Etc/GMT-4", "Etc/UTC", "Europe/Berlin", "UTC"];

function stubZones(detected = "Asia/Dubai") {
  vi.spyOn(Intl as unknown as { supportedValuesOf: () => string[] }, "supportedValuesOf").mockReturnValue(ZONES);
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
    timeZone: detected,
  } as Intl.ResolvedDateTimeFormatOptions);
}

afterEach(() => vi.restoreAllMocks());

describe("getTimezoneOptions", () => {
  it("hides Etc/* zones whose POSIX sign is inverted", () => {
    stubZones();
    const values = getTimezoneOptions("Asia/Dubai").map((o) => o.value);
    expect(values).toEqual(["Asia/Dubai", "Europe/Berlin", "UTC"]);
  });

  it("keeps a saved Etc/GMT zone and labels it with the real UTC offset", () => {
    stubZones();
    const options = getTimezoneOptions("Etc/GMT-4");
    expect(options).toContainEqual({ value: "Etc/GMT-4", label: "Etc/GMT-4 (UTC+4)" });
    expect(options.map((o) => o.value)).not.toContain("Etc/GMT+4");
  });

  it("labels Etc/GMT+N as a negative offset", () => {
    stubZones();
    expect(getTimezoneOptions("Etc/GMT+4")).toContainEqual({ value: "Etc/GMT+4", label: "Etc/GMT+4 (UTC−4)" });
  });
});
