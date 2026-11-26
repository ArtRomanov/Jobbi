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

  it("splits on exactly Python's str.split() whitespace", () => {
    // Python: U+001C-U+001F and U+0085 are whitespace, U+FEFF is not
    expect(normalizeKeywords(["front\u001cend", "a\u001f\u0085b", "\u3000vue\u2029"])).toEqual([
      "front end",
      "a b",
      "vue",
    ]);
    expect(normalizeKeywords(["\ufeffreact", "re\ufeffact"])).toEqual(["\ufeffreact", "re\ufeffact"]);
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

  it("trims the description exactly like Python's str.strip()", () => {
    const draft = (description: string) => ({ ...SAME_DRAFT, description });
    expect(hasSearchSettingsChanges(draft("\u0085Senior React\u001f"), SAVED)).toBe(false);
    expect(hasSearchSettingsChanges(draft("\u00a0\u202fSenior React\u3000"), SAVED)).toBe(false);
    // U+FEFF is not whitespace for Python, so the server keeps it
    expect(hasSearchSettingsChanges(draft("\ufeffSenior React"), SAVED)).toBe(true);
    // Only Python whitespace → blank → the same as no description
    expect(hasSearchSettingsChanges(draft("\u001c\u0085"), { ...SAVED, description: null })).toBe(false);
  });

  it("sees a changed description, keyword, keyword order or switch", () => {
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, description: "Senior Vue" }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywords: ["react"] }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywords: ["react", "vue"] }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywords: ["front end", "react"] }, SAVED)).toBe(true);
    expect(hasSearchSettingsChanges({ ...SAME_DRAFT, keywordFilter: false }, SAVED)).toBe(true);
  });
});
