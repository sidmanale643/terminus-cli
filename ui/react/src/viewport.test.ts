import assert from "node:assert/strict";
import {
  applyScrollAction,
  createViewportWindow,
  keepScrollPositionAfterRowChange,
  nextSmoothScrollOffset,
  visibleOptionRange,
  wrapTextToRows,
  type RenderedTranscriptLine,
} from "./viewport.js";

function line(id: string): RenderedTranscriptLine {
  return { id, sourceId: id, text: id, payload: {} };
}

assert.deepEqual(
  wrapTextToRows("abcdefghij", 4),
  ["abcd", "efgh", "ij"],
);

assert.deepEqual(
  wrapTextToRows("one\ntwo", 20),
  ["one", "two"],
);

const tenLines = Array.from({ length: 10 }, (_, index) => line(`row-${index}`));

assert.deepEqual(
  createViewportWindow(tenLines, 4, 0).lines.map((item) => item.id),
  ["row-6", "row-7", "row-8", "row-9"],
);

assert.deepEqual(
  createViewportWindow(tenLines, 4, 3).lines.map((item) => item.id),
  ["row-3", "row-4", "row-5", "row-6"],
);

assert.equal(applyScrollAction(0, { type: "line_up", rows: 3 }, 10, 4), 3);
assert.equal(applyScrollAction(3, { type: "line_down" }, 10, 4), 2);
assert.equal(applyScrollAction(0, { type: "home" }, 10, 4), 6);
assert.equal(applyScrollAction(6, { type: "end" }, 10, 4), 0);
assert.equal(applyScrollAction(0, { type: "page_up" }, 10, 4), 3);
assert.equal(applyScrollAction(3, { type: "page_down" }, 10, 4), 0);
assert.equal(
  nextSmoothScrollOffset({
    currentOffset: 0,
    targetOffset: 20,
    totalRows: 40,
    viewportRows: 8,
  }),
  6,
);
assert.equal(
  nextSmoothScrollOffset({
    currentOffset: 18,
    targetOffset: 20,
    totalRows: 40,
    viewportRows: 8,
  }),
  19,
);

assert.equal(
  keepScrollPositionAfterRowChange({
    previousOffset: 0,
    previousTotalRows: 10,
    nextTotalRows: 14,
    viewportRows: 4,
  }),
  0,
);

assert.equal(
  keepScrollPositionAfterRowChange({
    previousOffset: 2,
    previousTotalRows: 10,
    nextTotalRows: 14,
    viewportRows: 4,
  }),
  6,
);

assert.deepEqual(visibleOptionRange(30, 0, 10), { start: 0, end: 10 });
assert.deepEqual(visibleOptionRange(30, 15, 10), { start: 10, end: 20 });
assert.deepEqual(visibleOptionRange(30, 29, 10), { start: 20, end: 30 });
