// The designed CV's fonts as base64 `data:` URLs, embedded in the downloaded
// HTML so it is one self-contained file. ~186 KB of base64: this module is
// imported ONLY lazily from `download-cv-html.ts`, never statically.
import condensedLatin400 from "@/shared/assets/fonts/roboto-condensed-latin-400-normal.woff2?inline";
import condensedCyrillic400 from "@/shared/assets/fonts/roboto-condensed-cyrillic-400-normal.woff2?inline";
import condensedLatin500 from "@/shared/assets/fonts/roboto-condensed-latin-500-normal.woff2?inline";
import condensedCyrillic500 from "@/shared/assets/fonts/roboto-condensed-cyrillic-500-normal.woff2?inline";
import condensedLatin700 from "@/shared/assets/fonts/roboto-condensed-latin-700-normal.woff2?inline";
import condensedCyrillic700 from "@/shared/assets/fonts/roboto-condensed-cyrillic-700-normal.woff2?inline";
import monoLatin400 from "@/shared/assets/fonts/roboto-mono-latin-400-normal.woff2?inline";
import monoCyrillic400 from "@/shared/assets/fonts/roboto-mono-cyrillic-400-normal.woff2?inline";
import monoLatin700 from "@/shared/assets/fonts/roboto-mono-latin-700-normal.woff2?inline";
import monoCyrillic700 from "@/shared/assets/fonts/roboto-mono-cyrillic-700-normal.woff2?inline";
import type { CvFontSources } from "@/entities/cv";
export const CV_FONT_DATA_URLS: CvFontSources = {
  condensedLatin400,
  condensedCyrillic400,
  condensedLatin500,
  condensedCyrillic500,
  condensedLatin700,
  condensedCyrillic700,
  monoLatin400,
  monoCyrillic400,
  monoLatin700,
  monoCyrillic700,
};
