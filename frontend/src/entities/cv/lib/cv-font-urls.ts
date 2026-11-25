// The designed CV's fonts as asset URLs for the editor preview: Vite emits the
// woff2 files as assets and the browser fetches only the subsets it needs.
import condensedLatin400 from "@/shared/assets/fonts/roboto-condensed-latin-400-normal.woff2?url";
import condensedCyrillic400 from "@/shared/assets/fonts/roboto-condensed-cyrillic-400-normal.woff2?url";
import condensedLatin500 from "@/shared/assets/fonts/roboto-condensed-latin-500-normal.woff2?url";
import condensedCyrillic500 from "@/shared/assets/fonts/roboto-condensed-cyrillic-500-normal.woff2?url";
import condensedLatin700 from "@/shared/assets/fonts/roboto-condensed-latin-700-normal.woff2?url";
import condensedCyrillic700 from "@/shared/assets/fonts/roboto-condensed-cyrillic-700-normal.woff2?url";
import monoLatin400 from "@/shared/assets/fonts/roboto-mono-latin-400-normal.woff2?url";
import monoCyrillic400 from "@/shared/assets/fonts/roboto-mono-cyrillic-400-normal.woff2?url";
import monoLatin700 from "@/shared/assets/fonts/roboto-mono-latin-700-normal.woff2?url";
import monoCyrillic700 from "@/shared/assets/fonts/roboto-mono-cyrillic-700-normal.woff2?url";
import type { CvFontSources } from "./cv-layout-fonts";
export const CV_FONT_URLS: CvFontSources = {
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
