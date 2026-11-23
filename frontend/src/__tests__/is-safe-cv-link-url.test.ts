import { isSafeCvLinkUrl } from "@/shared/lib";

describe("isSafeCvLinkUrl", () => {
  it.each([
    "https://linkedin.com/in/jane",
    "http://example.com",
    "HTTPS://EXAMPLE.COM/Path",
    "mailto:jane@example.com",
    "MailTo:jane@example.com",
  ])("allows %s", (url) => {
    expect(isSafeCvLinkUrl(url)).toBe(true);
  });

  it.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "DATA:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://example.com",
    "tel:+37499123456",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "\u0000javascript:alert(1)",
    "javascript\u0001:alert(1)",
    " https://example.com",
    "https://example.com\u007f",
    "//example.com",
    "/relative/path",
    "example.com",
    "",
  ])("rejects %j", (url) => {
    expect(isSafeCvLinkUrl(url)).toBe(false);
  });
});
