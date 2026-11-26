import {
  hasSearchSettingsChanges,
  normalizeKeywords,
} from "@/features/manage-sources/lib/search-settings-changes";

const SAVED = { description: "Senior React", keywords: ["react", "front end"], keyword_filter: true };
const SAME_DRAFT = { description: "Senior React", keywords: ["react", "front end"], keywordFilter: true };

describe("normalizeKeywords", () => {
  it("trims, collapses inner whitespace, lowercases and de-dupes keeping order", () => {
    expect(normalizeKeywords(["  React ", "Front \t  End", "REACT", "vue"])).toEqual([
      "react",
      "front end",
      "vue",
    ]);
  });
});

describe("hasSearchSettingsChanges", () => {
  it("is false for the saved values", () => {
    expect(hasSearchSettingsChanges(SAME_DRAFT, SAVED)).toBe(false);
  });

  it("ignores what the server normalizes away", () => {
    expect(
      hasSearchSettingsChanges(
        { description: "  Senior React \n", keywords: [" React", "FRONT   END", "react"], keywordFilter: true },
        SAVED,
      ),
    ).toBe(false);
  });

  it("treats a blank description as the saved null / missing one", () => {
    const draft = { description: "   ", keywords: [], keywordFilter: true };
    expect(hasSearchSettingsChanges(draft, { description: null, keywords: [], keyword_filter: true })).toBe(false);
    expect(hasSearchSettingsChanges(draft, { keyword_filter: true })).toBe(false);
  });

  it("sees a changed description, keyword, keyword order or switch", () => {
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, description: "Senior Vue" }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywords: ["react"] }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywords: ["react", "vue"] }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywords: ["front end", "react"] }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywordFilter: false }, SAVED)).toBe(true);
  });
});
