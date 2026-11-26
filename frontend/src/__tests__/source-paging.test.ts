import {
  clampPage,
  getPageCount,
  getPageItems,
  getPageOfIndex,
} from "@/features/manage-sources/lib/paging";

describe("source paging math", () => {
  it.each([
    [0, 1],
    [1, 1],
    [7, 1],
    [8, 2],
    [14, 2],
    [15, 3],
    [50, 8],
  ])("getPageCount(%i, 7) = %i (never below 1)", (total, expected) => {
    expect(getPageCount(total, 7)).toBe(expected);
  });

  it.each([
    [0, 0],
    [6, 0],
    [7, 1],
    [13, 1],
    [14, 2],
  ])("getPageOfIndex(%i, 7) = %i", (index, expected) => {
    expect(getPageOfIndex(index, 7)).toBe(expected);
  });

  it.each([
    [0, 3, 0],
    [2, 3, 2],
    [3, 3, 2],
    [9, 2, 1],
    [-1, 3, 0],
    [1, 1, 0],
  ])("clampPage(%i, %i) = %i", (page, pageCount, expected) => {
    expect(clampPage(page, pageCount)).toBe(expected);
  });

  it("slices the items of one page; the last page may be short", () => {
    const items = Array.from({ length: 16 }, (_, i) => i);
    expect(getPageItems(items, 0, 7)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(getPageItems(items, 1, 7)).toEqual([7, 8, 9, 10, 11, 12, 13]);
    expect(getPageItems(items, 2, 7)).toEqual([14, 15]);
    expect(getPageItems([], 0, 7)).toEqual([]);
  });
});
