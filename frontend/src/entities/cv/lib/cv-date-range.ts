// Date-range detection for CV entries ("Jan 2020 – Present", "Март 2019 — по н.в.",
// "01/2019 - 03/2021", "с 2020 по 2022"). Used only to decide LAYOUT (dates go
// to the right of the entry title); the text itself is never changed.

const MONTH_EN =
  "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?";
// Nominative, genitive and prepositional forms plus the usual abbreviations
const MONTH_RU =
  "январ[ьяе]|янв|феврал[ьяе]|фев|март[ае]?|мар|апрел[ьяе]|апр|ма[йяе]|июн[ьяе]?|июл[ьяе]?|август[ае]?|авг|сентябр[ьяе]|сент?|октябр[ьяе]|окт|ноябр[ьяе]|нояб?|декабр[ьяе]|дек";
const YEAR = "(?:19|20)\\d{2}(?:\\s*г(?:ода|\\.)?)?";
const NUMERIC_DATE = "\\d{1,2}[./]\\d{4}|\\d{4}[-./]\\d{1,2}";
const DATE = `(?:(?:${MONTH_EN}|${MONTH_RU})\\.?,?\\s+${YEAR}|${NUMERIC_DATE}|${YEAR})`;
const PRESENT =
  "present|current(?:ly)?|now|today|ongoing|till now|to date|настоящее\\s+время|наст\\.?\\s*вр(?:емя|\\.)?|н\\.\\s*в\\.?|сейчас|текущее\\s+время";
const END = `(?:по\\s+)?(?:${PRESENT}|${DATE})`;
const SEPARATOR = "\\s*(?:[-–—−]+|to|until|till|до|по)\\s*";
const START_WORD = "(?:(?:since|from|с|со)\\s+)?";
// Something short may follow the range: "(2 years)", ", Berlin", " · Remote"
const TAIL = "(?:\\s*(?:[,;·|•(]|[-–—]\\s).*)?";

const DATE_RANGE_LINE = new RegExp(
  `^\\s*[([]?\\s*${START_WORD}${DATE}${SEPARATOR}${END}\\s*[)\\]]?${TAIL}$`,
  "iu",
);

/** A dates line is short; a long line that merely starts with a year is prose. */
export const MAX_DATE_LINE_LENGTH = 80;

/**
 * True when `line` is a date range (optionally followed by a short note), e.g.
 * "Jan 2020 – Present", "2019 — 2021, Remote", "Март 2019 – по настоящее время".
 */
export function isDateRangeLine(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.length > 0 && trimmed.length <= MAX_DATE_LINE_LENGTH && DATE_RANGE_LINE.test(trimmed);
}
