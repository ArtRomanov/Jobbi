export interface TextInsertion {
  /** The full new value. */
  value: string;
  /** Caret position right after the inserted text. */
  caret: number;
}

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

/**
 * Replaces `value[selectionStart, selectionEnd)` with `inserted`, cutting
 * `inserted` so the result is at most `maxLength` UTF-16 units long (the
 * unit `maxLength` on a textarea counts). Never cuts an emoji / surrogate
 * pair in half.
 */
export function insertTextWithinLimit(
  value: string,
  inserted: string,
  selectionStart: number,
  selectionEnd: number,
  maxLength: number,
): TextInsertion {
  const before = value.slice(0, selectionStart);
  const after = value.slice(selectionEnd);
  const room = Math.max(0, maxLength - before.length - after.length);

  let kept = inserted.slice(0, room);
  if (kept.length < inserted.length && kept.length > 0 && isHighSurrogate(kept.charCodeAt(kept.length - 1))) {
    kept = kept.slice(0, -1);
  }

  return { value: before + kept + after, caret: before.length + kept.length };
}
