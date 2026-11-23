import { Font } from "@react-pdf/renderer";
// `?url` keeps the TTF bytes out of JS: Vite emits them as assets and they
// are fetched only when react-pdf lays out text. This module is imported only
// from the lazy PDF chunk (see download-cv-text-pdf.ts).
import regularUrl from "@/shared/assets/fonts/NotoSans-Regular.ttf?url";
import boldUrl from "@/shared/assets/fonts/NotoSans-Bold.ttf?url";
import italicUrl from "@/shared/assets/fonts/NotoSans-Italic.ttf?url";
import boldItalicUrl from "@/shared/assets/fonts/NotoSans-BoldItalic.ttf?url";

export const CV_PDF_FONT_FAMILY = "NotoSans";

let isRegistered = false;

/**
 * Registers Noto Sans (Latin + Cyrillic) for the CV PDF once and turns off
 * react-pdf's hyphenation (it would split words with "-" at line ends).
 */
export function registerCvFonts(): void {
  if (isRegistered) return;
  Font.register({
    family: CV_PDF_FONT_FAMILY,
    fonts: [
      { src: regularUrl, fontWeight: 400, fontStyle: "normal" },
      { src: boldUrl, fontWeight: 700, fontStyle: "normal" },
      { src: italicUrl, fontWeight: 400, fontStyle: "italic" },
      { src: boldItalicUrl, fontWeight: 700, fontStyle: "italic" },
    ],
  });
  Font.registerHyphenationCallback((word) => [word]);
  isRegistered = true;
}
