import { isSafeExternalUrl } from "@/shared/lib";

describe("isSafeExternalUrl", () => {
  it.each(["https://acme.com/jobs/1", "http://example.org", "HTTPS://ACME.COM"])(
    "accepts absolute http(s) URL %s",
    (url) => {
      expect(isSafeExternalUrl(url)).toBe(true);
    },
  );

  it.each([
    "javascript:alert(1)",
    " javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<b>x</b>",
    "vbscript:msgbox(1)",
    "ftp://files.example.org",
    "/jobs/1",
    "jobs/1",
    "//evil.example",
    "",
  ])("rejects %j", (url) => {
    expect(isSafeExternalUrl(url)).toBe(false);
  });
});
