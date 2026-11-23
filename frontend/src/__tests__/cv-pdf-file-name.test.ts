import { getCvPdfFileName } from "@/features/cv-pdf";

describe("getCvPdfFileName", () => {
  it("keeps the name as is when it is valid", () => {
    expect(getCvPdfFileName("Jane Doe - Frontend (2026)")).toBe("Jane Doe - Frontend (2026).pdf");
  });

  it("keeps Cyrillic", () => {
    expect(getCvPdfFileName("Резюме Иван — Kleos")).toBe("Резюме Иван — Kleos.pdf");
  });

  it("replaces each invalid character with _", () => {
    expect(getCvPdfFileName('a/b\\c:d*e?f"g<h>i|j')).toBe("a_b_c_d_e_f_g_h_i_j.pdf");
  });

  it("replaces control characters", () => {
    expect(getCvPdfFileName("CV\u0000\u001f\u007fx")).toBe("CV___x.pdf");
  });

  it.each(["", "   "])("falls back to CV for %j", (name) => {
    expect(getCvPdfFileName(name)).toBe("CV.pdf");
  });
});
