import { appendUniqueTerms } from "@/shared/lib";

describe("appendUniqueTerms", () => {
  it("trims, skips empty terms and case-insensitive duplicates", () => {
    expect(appendUniqueTerms(["Java"], [" php ", "", "  ", "JAVA", "PHP", "go"])).toEqual([
      "Java",
      "php",
      "go",
    ]);
  });

  it("returns the same array when nothing is added", () => {
    const values = ["java"];
    expect(appendUniqueTerms(values, ["Java", " "])).toBe(values);
  });

  it("stops at maxItems and cuts terms to maxLength", () => {
    expect(appendUniqueTerms(["a"], ["bbbb", "c", "d"], { maxItems: 3, maxLength: 2 })).toEqual([
      "a",
      "bb",
      "c",
    ]);
  });
});
