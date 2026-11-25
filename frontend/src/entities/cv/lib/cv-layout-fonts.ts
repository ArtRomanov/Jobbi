// Font files of the designed CV: Roboto Condensed 400/500/700 (headings) and
// Roboto Mono 400/700 (body), Latin + Cyrillic subsets, static woff2 from
// @fontsource 5.3.0 (SIL OFL 1.1, licences beside the files in
// shared/assets/fonts). Where the bytes come from (a URL for the preview,
// base64 for the download) is the caller's choice: see `buildCvFontFaceCss`.

const LATIN_RANGE =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";
const CYRILLIC_RANGE = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116";

export const CV_FONT_FILES = [
  { key: "condensedLatin400", family: "Roboto Condensed", weight: 400, range: LATIN_RANGE },
  { key: "condensedCyrillic400", family: "Roboto Condensed", weight: 400, range: CYRILLIC_RANGE },
  { key: "condensedLatin500", family: "Roboto Condensed", weight: 500, range: LATIN_RANGE },
  { key: "condensedCyrillic500", family: "Roboto Condensed", weight: 500, range: CYRILLIC_RANGE },
  { key: "condensedLatin700", family: "Roboto Condensed", weight: 700, range: LATIN_RANGE },
  { key: "condensedCyrillic700", family: "Roboto Condensed", weight: 700, range: CYRILLIC_RANGE },
  { key: "monoLatin400", family: "Roboto Mono", weight: 400, range: LATIN_RANGE },
  { key: "monoCyrillic400", family: "Roboto Mono", weight: 400, range: CYRILLIC_RANGE },
  { key: "monoLatin700", family: "Roboto Mono", weight: 700, range: LATIN_RANGE },
  { key: "monoCyrillic700", family: "Roboto Mono", weight: 700, range: CYRILLIC_RANGE },
] as const;

export type CvFontFileKey = (typeof CV_FONT_FILES)[number]["key"];

/** Where each font file is loaded from: an asset URL or a `data:` URL. */
export type CvFontSources = Readonly<Record<CvFontFileKey, string>>;

/** Only our own asset/data URLs: anything that could break out of `url("…")` is refused. */
const SAFE_FONT_SOURCE = /^(?:data:font\/woff2;base64,[A-Za-z0-9+/=]+|[A-Za-z0-9_\-./:?&=%]+)$/;

/** `@font-face` rules for every CV font file, from the given sources. */
export function buildCvFontFaceCss(sources: CvFontSources): string {
  return CV_FONT_FILES.map(({ key, family, weight, range }) => {
    const src = sources[key];
    if (!SAFE_FONT_SOURCE.test(src)) return "";
    return `@font-face{font-family:"${family}";font-style:normal;font-weight:${weight};font-display:swap;src:url("${src}") format("woff2");unicode-range:${range}}`;
  }).join("\n");
}
