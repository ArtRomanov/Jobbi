import { toFieldErrors, webSourceOptionsSchema } from "@/features/manage-sources/model/schemas";

describe("toFieldErrors", () => {
  it("keeps the first message of each known field and ignores other paths", () => {
    expect(
      toFieldErrors([
        { path: ["jobLinkContains"], message: "first" },
        { path: ["jobLinkContains"], message: "second" },
        { path: ["other"], message: "ignored" },
        { path: [], message: "root" },
        { path: ["name"], message: "name error" },
      ]),
    ).toEqual({ jobLinkContains: "first", name: "name error" });
  });

  it("maps real schema issues to both fields", () => {
    const tooLong = "x".repeat(101);
    const parsed = webSourceOptionsSchema.safeParse({ jobLinkContains: tooLong, name: tooLong });

    expect(parsed.success).toBe(false);
    const errors = toFieldErrors(parsed.error?.issues ?? []);
    expect(Object.keys(errors).sort()).toEqual(["jobLinkContains", "name"]);
  });

  it("returns no errors for no issues", () => {
    expect(toFieldErrors([])).toEqual({});
  });
});
