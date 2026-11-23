import { Font } from "@react-pdf/renderer";
// `?url` keeps the TTF bytes out of JS: Vite emits them as assets and they
// are fetched only when react-pdf lays out text. This module is imported only
// from the lazy PDF chunk (see download-cv-text-pdf.ts).
import regularUrl from "@/shared/assets/fonts/NotoSans-Regular.ttf?url";
import boldUrl from "@/shared/assets/fonts/NotoSans-Bold.ttf?url";
import italicUrl from "@/shared/assets/fonts/NotoSans-Italic.ttf?url";
import boldItalicUrl from "@/shared/assets/fonts/NotoSans-BoldItalic.ttf?url";

export const CV_PDF_FONT_FAMILY = "NotoSans";

export interface CvFontSources {
  regular: string;
  bold: string;
  italic: string;
  boldItalic: string;
}

const BUNDLED_SOURCES: CvFontSources = {
  regular: regularUrl,
  bold: boldUrl,
  italic: italicUrl,
  boldItalic: boldItalicUrl,
};

let isRegistered = false;

/**
 * Registers Noto Sans (Latin + Cyrillic) for the CV PDF once and turns off
 * react-pdf's hyphenation (it would split words with "-" at line ends).
 * `sources` exists for tests that load the TTFs from disk.
 */
export function registerCvFonts(sources: CvFontSources = BUNDLED_SOURCES): void {
  if (isRegistered) return;
  Font.register({
    family: CV_PDF_FONT_FAMILY,
    fonts: [
      { src: sources.regular, fontWeight: 400, fontStyle: "normal" },
      { src: sources.bold, fontWeight: 700, fontStyle: "normal" },
      { src: sources.italic, fontWeight: 400, fontStyle: "italic" },
      { src: sources.boldItalic, fontWeight: 700, fontStyle: "italic" },
    ],
  });
  Font.registerHyphenationCallback((word) => [word]);
  isRegistered = true;
}
