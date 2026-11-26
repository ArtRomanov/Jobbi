import { hasEditSourceChanges } from "@/features/manage-sources/lib/edit-source-changes";

const INITIAL = { name: "Geekjob React", link: "https://geekjob.ru/vacancies", jobLinkContains: "/vacancy/" };

describe("hasEditSourceChanges", () => {
  it("is false for the starting values", () => {
    expect(hasEditSourceChanges(INITIAL, INITIAL, true)).toBe(false);
  });

  it("ignores spaces around any field (the schema trims them)", () => {
    expect(
      hasEditSourceChanges(
        { name: " Geekjob React  ", link: "https://geekjob.ru/vacancies ", jobLinkContains: " /vacancy/" },
        INITIAL,
        true,
      ),
    ).toBe(false);
  });

  it("treats a blank name or pattern as empty", () => {
    const initial = { name: "", link: "@jobs", jobLinkContains: "" };
    expect(hasEditSourceChanges({ name: "   ", link: "@jobs", jobLinkContains: "  " }, initial, true)).toBe(
      false,
    );
  });

  it("sees a changed name, link or (web only) pattern", () => {
    expect(hasEditSourceChanges({ ...INITIAL, name: "Geekjob" }, INITIAL, true)).toBe(true);
    expect(hasEditSourceChanges({ ...INITIAL, name: "  " }, INITIAL, true)).toBe(true);
    expect(hasEditSourceChanges({ ...INITIAL, link: "https://geekjob.ru/vue" }, INITIAL, true)).toBe(true);
    expect(hasEditSourceChanges({ ...INITIAL, jobLinkContains: "/job/" }, INITIAL, true)).toBe(true);
    // A non-web source has no pattern field
    expect(hasEditSourceChanges({ ...INITIAL, jobLinkContains: "/job/" }, INITIAL, false)).toBe(false);
  });
});
