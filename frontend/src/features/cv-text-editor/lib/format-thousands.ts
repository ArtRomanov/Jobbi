/** 18001 → "18 001": groups of three digits split by a space, as in "20 000". */
export function formatThousands(value: number): string {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}
