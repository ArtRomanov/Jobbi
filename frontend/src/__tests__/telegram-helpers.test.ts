import { parseUtcDate } from "@/features/telegram-connect/lib/helpers";

// 2026-03-10 12:10:00 UTC. Compared against a fixed epoch, not another
// `new Date(...)`, so a naive-as-local parse fails on any non-UTC machine
// (run with e.g. TZ=Asia/Tokyo to exercise it).
const EXPECTED_UTC_MS = Date.UTC(2026, 2, 10, 12, 10, 0);

describe("parseUtcDate", () => {
  it.each([
    ["naive (legacy backend)", "2026-03-10T12:10:00"],
    ["Z suffix", "2026-03-10T12:10:00Z"],
    ["+00:00 offset", "2026-03-10T12:10:00+00:00"],
  ])("parses the %s form as UTC", (_label, value) => {
    expect(parseUtcDate(value).getTime()).toBe(EXPECTED_UTC_MS);
  });

  it("keeps an explicit non-UTC offset", () => {
    // 16:10 at +04:00 is 12:10 UTC
    expect(parseUtcDate("2026-03-10T16:10:00+04:00").getTime()).toBe(EXPECTED_UTC_MS);
  });

  it("returns an invalid date for garbage input", () => {
    expect(parseUtcDate("not-a-date").getTime()).toBeNaN();
  });
});
