export type ScrollAction =
  | { type: "line_up"; rows?: number }
  | { type: "line_down"; rows?: number }
  | { type: "page_up" }
  | { type: "page_down" }
  | { type: "home" }
  | { type: "end" };

export interface RenderedTranscriptLine<TPayload = unknown> {
  id: string;
  sourceId: string;
  text: string;
  payload: TPayload;
}

export interface ViewportWindow<TLine> {
  lines: TLine[];
  totalRows: number;
  viewportRows: number;
  scrollOffset: number;
  hiddenTopRows: number;
  hiddenBottomRows: number;
  startRow: number;
}

export interface SmoothScrollStepOptions {
  currentOffset: number;
  targetOffset: number;
  totalRows: number;
  viewportRows: number;
}

export function wrapTextToRows(text: string, width: number): string[] {
  const rowWidth = Math.max(1, Math.floor(width));
  return text.split("\n").flatMap((line) => wrapSingleLine(line, rowWidth));
}

export function createViewportWindow<TLine>(
  lines: TLine[],
  viewportRows: number,
  scrollOffset: number,
): ViewportWindow<TLine> {
  const totalRows = lines.length;
  const rows = Math.max(0, Math.floor(viewportRows));
  const clampedOffset = clampScrollOffset(scrollOffset, totalRows, rows);
  const startRow = Math.max(0, totalRows - rows - clampedOffset);
  const endRow = rows === 0 ? startRow : Math.min(totalRows, startRow + rows);

  return {
    lines: lines.slice(startRow, endRow),
    totalRows,
    viewportRows: rows,
    scrollOffset: clampedOffset,
    hiddenTopRows: startRow,
    hiddenBottomRows: Math.max(0, totalRows - endRow),
    startRow,
  };
}

export function applyScrollAction(
  currentOffset: number,
  action: ScrollAction,
  totalRows: number,
  viewportRows: number,
): number {
  const pageRows = Math.max(1, viewportRows - 1);
  const maxOffset = maxScrollOffset(totalRows, viewportRows);

  switch (action.type) {
    case "line_up":
      return clampToMax(currentOffset + (action.rows ?? 1), maxOffset);
    case "line_down":
      return clampToMax(currentOffset - (action.rows ?? 1), maxOffset);
    case "page_up":
      return clampToMax(currentOffset + pageRows, maxOffset);
    case "page_down":
      return clampToMax(currentOffset - pageRows, maxOffset);
    case "home":
      return maxOffset;
    case "end":
      return 0;
  }
}

export function keepScrollPositionAfterRowChange(options: {
  previousOffset: number;
  previousTotalRows: number;
  nextTotalRows: number;
  viewportRows: number;
}): number {
  if (options.previousOffset <= 0) return 0;

  const rowDelta = options.nextTotalRows - options.previousTotalRows;
  return clampScrollOffset(
    options.previousOffset + Math.max(0, rowDelta),
    options.nextTotalRows,
    options.viewportRows,
  );
}

export function maxScrollOffset(totalRows: number, viewportRows: number): number {
  return Math.max(0, totalRows - Math.max(0, viewportRows));
}

export function clampScrollOffset(offset: number, totalRows: number, viewportRows: number): number {
  return clampToMax(offset, maxScrollOffset(totalRows, viewportRows));
}

export function visibleOptionRange(optionsLength: number, selectedIndex: number, viewportRows: number): {
  start: number;
  end: number;
} {
  const rows = Math.max(1, Math.floor(viewportRows));
  const clampedIndex = clampToMax(selectedIndex, Math.max(0, optionsLength - 1));
  const preferredStart = clampedIndex - Math.floor(rows / 2);
  const start = clampToMax(Math.max(0, preferredStart), Math.max(0, optionsLength - rows));
  return { start, end: Math.min(optionsLength, start + rows) };
}

export function nextSmoothScrollOffset(options: SmoothScrollStepOptions): number {
  const current = clampScrollOffset(options.currentOffset, options.totalRows, options.viewportRows);
  const target = clampScrollOffset(options.targetOffset, options.totalRows, options.viewportRows);
  const distance = target - current;

  if (distance === 0) return current;
  return current + Math.sign(distance) * smoothScrollStepSize(Math.abs(distance));
}

function smoothScrollStepSize(distance: number): number {
  if (distance > 18) return 6;
  if (distance > 8) return 4;
  if (distance > 3) return 2;
  return 1;
}

function wrapSingleLine(line: string, width: number): string[] {
  if (line.length === 0) return [""];

  const rows: string[] = [];
  for (let index = 0; index < line.length; index += width) {
    rows.push(line.slice(index, index + width));
  }
  return rows;
}

function clampToMax(value: number, maxValue: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(Math.max(0, Math.floor(value)), Math.max(0, maxValue));
}
