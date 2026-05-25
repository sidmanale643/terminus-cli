import { Fragment, memo, useEffect, useReducer, useRef, useState } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import { Box, Text, useApp, useInput, useStdout } from "ink";
import { SocketClient } from "./socket-client.js";
import type {
  CommandOption,
  GuidedQuestion,
  InboundEnvelope,
  ModelOption,
  OutboundMessage,
  ProviderOption,
  SkillOption,
} from "./protocol.js";
import {
  initialState,
  reducer,
  selectWorkers,
  selectStreamingItems,
  selectTranscriptItems,
  type WorkerActivityItem,
  type WorkerState,
  type StreamingItem,
  type TranscriptItem,
  type TodoItem,
} from "./state.js";
import {
  calculateBottomWorkerPaneHeight,
  calculateMainContentRows,
  calculateSideBySideHeight,
  calculateSideWorkerPaneHeight,
  calculateTranscriptFrameHeight,
  calculateWorkerPaneLayout,
  TRANSCRIPT_CHROME_ROWS,
  type WorkerPaneLayout,
} from "./layout.js";
import {
  enableSgrMouseReporting,
  findTranscriptMouseHit,
  isSgrMouseInput,
  parseSgrMouseClick,
  parseSgrMouseWheels,
  type TranscriptHitArea,
} from "./mouse.js";
import {
  applyScrollAction,
  createViewportWindow,
  keepScrollPositionAfterRowChange,
  nextSmoothScrollOffset,
  visibleOptionRange,
  wrapTextToRows,
  type RenderedTranscriptLine,
  type ScrollAction,
} from "./viewport.js";
import {
  buildWorkerPaneRows,
  type WorkerPaneRow,
  type WorkerResultLine,
} from "./worker-view.js";

const COLORS = {
  background: "#0d1117",
  panel: "#161b22",
  panelMuted: "#1c2128",
  border: "#30363d",
  borderMuted: "#21262d",
  text: "#f0f6fc",
  dim: "#8b949e",
  muted: "#6e7681",
  accent: "#58a6ff",
  accentSoft: "#1f6feb",
  danger: "#ff7b72",
  success: "#7ee787",
  info: "#79c0ff",
};

const WIDE_BANNER_MIN_WIDTH = 78;
const WIDE_BANNER_ROWS = 8;
const COMPACT_BANNER_ROWS = 4;
const WELCOME_ROWS = 6;
const COMPACT_LABEL_LENGTH = 18;
const COMPACT_BODY_LENGTH = 52;
const TRANSCRIPT_CONTENT_COLUMN = 3;
const TRANSCRIPT_FIRST_CONTENT_ROW = 2;
const TRANSCRIPT_CHROME_COLUMNS = 4;
const TRANSCRIPT_WHEEL_ROWS = 2;
const TRANSCRIPT_SMOOTH_SCROLL_FRAME_MS = 12;
const MAX_SIDE_WORKER_PANE_ROWS = 14;
const MODAL_OPTION_ROWS = 10;
const REVIEW_SUBMIT_INDEX_OFFSET = 1;

function homeCompressed(pathValue: string): string {
  const home = process.env.HOME ?? "";
  return home && pathValue.startsWith(home) ? `~${pathValue.slice(home.length)}` : pathValue || ".";
}

function truncateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  if (maxLength <= 5) return value.slice(0, maxLength);
  const keep = Math.floor((maxLength - 1) / 2);
  const tail = maxLength - keep - 1;
  return `${value.slice(0, keep)}~${value.slice(value.length - tail)}`;
}

function shouldUseWideBanner(width: number): boolean {
  return width >= WIDE_BANNER_MIN_WIDTH;
}

export function calculateBannerRows(width: number, hasBanner: boolean): number {
  if (!hasBanner) return 0;
  return shouldUseWideBanner(width) ? WIDE_BANNER_ROWS : COMPACT_BANNER_ROWS;
}

function formatPercent(value: number): string {
  const normalized = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  return `${normalized}%`;
}

type InlineToken =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; label: string; url: string };

interface MarkdownTable {
  header: string[];
  rows: string[][];
  endIndex: number;
}

function compactLine(value: string, maxLength: number): string {
  if (maxLength <= 0) return "";
  const singleLine = value.replace(/\s+/g, " ").trim();
  if (singleLine.length <= maxLength) return singleLine;
  return `${singleLine.slice(0, Math.max(0, maxLength - 1))}…`;
}

function truncatePreservingWhitespace(value: string, maxLength: number): string {
  if (maxLength <= 0) return "";
  if (value.length <= maxLength) return value;
  return value.slice(0, maxLength);
}

function parseInlineMarkdown(value: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  const pattern = /(\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let lastIndex = 0;

  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      tokens.push({ type: "text", value: value.slice(lastIndex, index) });
    }

    if (match[2] && match[3]) {
      tokens.push({ type: "link", label: match[2], url: match[3] });
    } else if (match[4]) {
      tokens.push({ type: "bold", value: match[4] });
    } else if (match[5]) {
      tokens.push({ type: "code", value: match[5] });
    }

    lastIndex = index + match[0].length;
  }

  if (lastIndex < value.length) {
    tokens.push({ type: "text", value: value.slice(lastIndex) });
  }

  return tokens;
}

function MarkdownInline({ text, color }: { text: string; color: string }) {
  const tokens = parseInlineMarkdown(text);
  return (
    <>
      {tokens.map((token, index) => {
        if (token.type === "bold") {
          return (
            <Text key={`bold-${index}`} color={COLORS.text} bold>
              {token.value}
            </Text>
          );
        }
        if (token.type === "code") {
          return (
            <Text key={`code-${index}`} color={COLORS.accent} backgroundColor={COLORS.panel}>
              {token.value}
            </Text>
          );
        }
        if (token.type === "link") {
          return (
            <Text key={`link-${index}`} color={COLORS.info} underline>
              {`${token.label} (${token.url})`}
            </Text>
          );
        }
        return (
          <Text key={`text-${index}`} color={color}>
            {token.value}
          </Text>
        );
      })}
    </>
  );
}

export function markdownDisplayRows(markdown: string, width: number): string[] {
  const rows: string[] = [];
  const sourceRows = markdown.split("\n");
  const displayWidth = Math.max(1, width);
  for (let index = 0; index < sourceRows.length; index += 1) {
    const table = readMarkdownTable(sourceRows, index);
    if (table) {
      rows.push(...formatMarkdownTable(table, displayWidth));
      index = table.endIndex;
      continue;
    }
    rows.push(formatMarkdownBlockRow(sourceRows[index]));
  }
  return rows;
}

function formatMarkdownBlockRow(row: string): string {
  const heading = row.match(/^(#{1,6})\s+(.*)$/);
  if (heading) return heading[2] ?? "";
  return row;
}

function readMarkdownTable(rows: string[], startIndex: number): MarkdownTable | null {
  if (!isMarkdownTableRow(rows[startIndex]) || !isMarkdownTableSeparator(rows[startIndex + 1])) {
    return null;
  }

  const header = parseMarkdownTableRow(rows[startIndex]);
  const bodyRows: string[][] = [];
  let endIndex = startIndex + 1;

  for (let index = startIndex + 2; index < rows.length; index += 1) {
    if (!isMarkdownTableRow(rows[index])) break;
    bodyRows.push(parseMarkdownTableRow(rows[index]));
    endIndex = index;
  }

  return { header, rows: bodyRows, endIndex };
}

function isMarkdownTableRow(row: string | undefined): boolean {
  return Boolean(row?.trim()) && (row?.includes("|") ?? false);
}

function isMarkdownTableSeparator(row: string | undefined): boolean {
  if (!row) return false;
  const cells = parseMarkdownTableRow(row);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")));
}

function parseMarkdownTableRow(row: string): string[] {
  const trimmed = row.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function formatMarkdownTable(table: MarkdownTable, width: number): string[] {
  const columnCount = Math.max(table.header.length, ...table.rows.map((row) => row.length));
  const columnWidths = markdownTableColumnWidths(table, columnCount, width);
  return [
    formatMarkdownTableRow(table.header, columnWidths),
    formatMarkdownTableSeparator(columnWidths),
    ...table.rows.map((row) => formatMarkdownTableRow(row, columnWidths)),
  ];
}

function markdownTableColumnWidths(table: MarkdownTable, columnCount: number, width: number): number[] {
  const naturalWidths = Array.from({ length: columnCount }, (_, columnIndex) => (
    Math.max(3, ...[table.header, ...table.rows].map((row) => (row[columnIndex] ?? "").length))
  ));
  const naturalTableWidth = naturalWidths.reduce((total, cellWidth) => total + cellWidth, 0) + columnCount * 3 + 1;
  if (naturalTableWidth <= width) return naturalWidths;

  const availableCellWidth = Math.max(columnCount * 3, width - columnCount * 3 - 1);
  const maxColumnWidth = Math.max(3, Math.floor(availableCellWidth / columnCount));
  return naturalWidths.map((cellWidth) => Math.min(cellWidth, maxColumnWidth));
}

function formatMarkdownTableRow(cells: string[], columnWidths: number[]): string {
  const paddedCells = columnWidths.map((width, index) => ` ${compactLine(cells[index] ?? "", width).padEnd(width)} `);
  return `|${paddedCells.join("|")}|`;
}

function formatMarkdownTableSeparator(columnWidths: number[]): string {
  return `|${columnWidths.map((width) => ` ${"-".repeat(width)} `).join("|")}|`;
}

function roleColor(item: TranscriptItem): string {
  switch (item.tone) {
    case "error":
      return COLORS.danger;
    case "warning":
      return COLORS.accent;
    case "tool":
      return COLORS.info;
    case "worker":
      return COLORS.success;
    case "thinking":
      return COLORS.dim;
    case "user":
      return COLORS.accent;
    default:
      return COLORS.text;
  }
}

type TranscriptGroup = "major" | "internal" | "worker" | "notice";

function transcriptMeta(item: TranscriptItem): {
  label: string;
  labelColor: string;
  bodyColor: string;
} {
  if (item.tone === "user") {
    return { label: "You", labelColor: COLORS.accent, bodyColor: COLORS.text };
  }
  if (item.kind === "thinking") {
    return { label: "Thinking", labelColor: COLORS.dim, bodyColor: COLORS.dim };
  }
  if (item.tone === "assistant" || item.kind === "response") {
    return { label: "Assistant", labelColor: COLORS.info, bodyColor: COLORS.text };
  }
  if (item.kind === "tool_call") {
    return { label: "Tool call", labelColor: COLORS.dim, bodyColor: COLORS.dim };
  }
  if (item.kind === "tool_output") {
    return { label: "Tool output", labelColor: COLORS.dim, bodyColor: COLORS.dim };
  }
  if (item.tone === "error") {
    return { label: "Error", labelColor: COLORS.danger, bodyColor: COLORS.danger };
  }
  if (item.tone === "warning") {
    return { label: item.title ?? "Notice", labelColor: COLORS.accent, bodyColor: COLORS.text };
  }
  if (item.tone === "worker") {
    return { label: "Worker", labelColor: COLORS.success, bodyColor: COLORS.text };
  }
  return { label: item.title ?? "System", labelColor: roleColor(item), bodyColor: COLORS.text };
}

function isCompactTranscriptItem(item: TranscriptItem): boolean {
  return item.kind === "thinking" || item.kind === "tool_call" || item.kind === "tool_output";
}

function transcriptGroup(item: TranscriptItem): TranscriptGroup {
  if (isCompactTranscriptItem(item)) return "internal";
  if (item.tone === "worker" || item.kind === "worker") return "worker";
  if (item.kind === "alert" || item.kind === "mode" || item.kind === "error") return "notice";
  return "major";
}

function transcriptGap(previous: TranscriptItem | undefined, current: TranscriptItem): number {
  if (!previous) return 0;

  const previousGroup = transcriptGroup(previous);
  const currentGroup = transcriptGroup(current);

  if (currentGroup === "internal" && previousGroup === "internal") return 0;
  if (currentGroup === "internal" && previousGroup === "major") return 0;
  if (currentGroup === "worker" && previousGroup === "internal") return 0;
  if (currentGroup === "worker" && previousGroup === "worker") return 0;
  if (currentGroup === "major" && previousGroup === "internal") return 1;
  if (currentGroup === "major" && previousGroup === "worker") return 1;
  if (currentGroup === "major" && previousGroup === "major") return 1;

  return currentGroup === previousGroup ? 0 : 1;
}

function compactJsonBody(value: string, maxLength = COMPACT_BODY_LENGTH): string {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && Object.keys(parsed).length === 0) {
      return "";
    }
    return compactLine(JSON.stringify(parsed), maxLength);
  } catch {
    return compactLine(value, maxLength);
  }
}

function toolOutputName(title?: string): string {
  return title?.replace(/\s+output$/i, "") || "tool";
}

function transcriptPreview(item: TranscriptItem, expanded: boolean): string {
  if (item.kind === "tool_call") {
    const args = expanded ? compactJsonBody(item.body, 900) : compactJsonBody(item.body);
    return [item.title, args].filter(Boolean).join(" ");
  }
  if (item.kind === "tool_output") {
    const output = expanded ? item.body : compactLine(item.preview || item.body, COMPACT_BODY_LENGTH);
    return [toolOutputName(item.title), output].filter(Boolean).join(" ");
  }
  return expanded ? item.body : compactLine(item.preview || item.body, COMPACT_BODY_LENGTH);
}

function isMouseWithinBounds(
  point: { x: number; y: number },
  bounds: { top: number; left: number; width: number; height: number },
): boolean {
  return (
    point.x >= bounds.left &&
    point.x < bounds.left + bounds.width &&
    point.y >= bounds.top &&
    point.y < bounds.top + bounds.height
  );
}

function Spinner({
  active,
  color = COLORS.accent,
}: {
  active: boolean;
  color?: string;
}) {
  const frames = ["|", "/", "-", "\\"];
  const [frameIndex, setFrameIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setFrameIndex(0);
      return;
    }

    const timer = setInterval(() => {
      setFrameIndex((current) => (current + 1) % frames.length);
    }, 80);

    return () => clearInterval(timer);
  }, [active]);

  return <Text color={color}>{frames[frameIndex]}</Text>;
}

function CommandSuggestions({
  commands,
  query,
  selectedIndex,
}: {
  commands: CommandOption[];
  query: string;
  selectedIndex: number;
}) {
  const filtered = commands.filter((command) => command.name.startsWith(query));
  if (filtered.length === 0) {
    return (
      <Box marginLeft={2}>
        <Text color={COLORS.dim}>No matching commands</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginLeft={2}>
      {filtered.slice(0, 8).map((command, index) => (
        <Text
          key={command.name}
          color={index === selectedIndex ? COLORS.background : COLORS.dim}
          backgroundColor={index === selectedIndex ? COLORS.accent : undefined}
        >
          {`${index === selectedIndex ? ">" : " "} ${command.name.padEnd(14)} ${command.description}`}
        </Text>
      ))}
    </Box>
  );
}

function InputPanel({
  active,
  commands,
  connectionError,
  isGenerating,
  cwd,
  model,
  contextPercent,
  width,
  onSubmit,
  onInterrupt,
  onCopyLast,
}: {
  active: boolean;
  commands: CommandOption[];
  connectionError: string | null;
  isGenerating: boolean;
  cwd: string;
  model: string;
  contextPercent: number;
  width: number;
  onSubmit: (value: string) => void;
  onInterrupt: () => void;
  onCopyLast: () => void;
}) {
  const [value, setValue] = useState("");
  const [cursor, setCursor] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const commandQuery = value.startsWith("/") ? value : "";
  const filtered = commandQuery
    ? commands.filter((command) => command.name.startsWith(commandQuery))
    : [];
  const showSuggestions = active && commandQuery.length > 0;
  const footerRight = `${formatPercent(contextPercent)}  ${model || "no-model"}`;
  const footerLeft = truncateMiddle(homeCompressed(cwd), Math.max(12, width - footerRight.length - 5));
  const footerGap = Math.max(1, width - footerLeft.length - footerRight.length - 4);
  const cursorGlyph = active ? "▌" : "▏";
  const cursorColor = active ? COLORS.accent : COLORS.dim;

  useEffect(() => {
    if (!active) return;
    setValue("");
    setCursor(0);
    setSelectedIndex(0);
  }, [active]);

  useInput((input, key) => {
    if (isSgrMouseInput(input)) return;
    if (!active) return;

    if (key.ctrl && input === "c") {
      onInterrupt();
      return;
    }
    if (key.ctrl && input === "y") {
      onCopyLast();
      return;
    }
    if (key.leftArrow) {
      setCursor((current) => Math.max(0, current - 1));
      return;
    }
    if (key.rightArrow) {
      setCursor((current) => Math.min(value.length, current + 1));
      return;
    }
    if (showSuggestions && key.upArrow) {
      setSelectedIndex((current) => Math.max(0, current - 1));
      return;
    }
    if (showSuggestions && key.downArrow) {
      setSelectedIndex((current) => Math.min(filtered.length - 1, current + 1));
      return;
    }
    if (key.backspace || key.delete) {
      if (cursor === 0) return;
      setValue((current) => current.slice(0, cursor - 1) + current.slice(cursor));
      setCursor((current) => current - 1);
      return;
    }
    if (key.return) {
      const submitted =
        showSuggestions && filtered[selectedIndex]
          ? filtered[selectedIndex].name
          : value.trim();
      if (!submitted) return;
      onSubmit(submitted);
      setValue("");
      setCursor(0);
      setSelectedIndex(0);
      return;
    }
    if (!key.ctrl && !key.meta && input.length > 0) {
      setValue((current) => current.slice(0, cursor) + input + current.slice(cursor));
      setCursor((current) => current + input.length);
    }
  });

  return (
    <>
      {isGenerating ? (
        <Box>
          <Spinner active={true} />
          <Text color={COLORS.dim}> Generating response  Ctrl+C interrupt</Text>
        </Box>
      ) : null}
      <Box flexDirection="column" borderStyle="round" borderColor={COLORS.border} paddingX={1} paddingY={1}>
        {connectionError ? <Text color={COLORS.danger}>{connectionError}</Text> : null}
        <Box>
          <Text color={COLORS.accent}>{"> "}</Text>
          <Text color={COLORS.text}>{value.slice(0, cursor)}</Text>
          <Text color={cursorColor}>{cursorGlyph}</Text>
          <Text color={COLORS.text}>{value.slice(cursor)}</Text>
        </Box>
        <Box marginTop={1}>
          <Text color={COLORS.dim}>{footerLeft}</Text>
          <Text>{" ".repeat(footerGap)}</Text>
          <Text color={COLORS.accent}>{formatPercent(contextPercent)}</Text>
          <Text color={COLORS.dim}>{"  "}</Text>
          <Text color={COLORS.text}>{model || "no-model"}</Text>
        </Box>
        {showSuggestions ? (
          <CommandSuggestions commands={commands} query={commandQuery} selectedIndex={selectedIndex} />
        ) : null}
      </Box>
      {active ? (
        <Text color={COLORS.dim}>
          Enter submit  Ctrl+C interrupt
        </Text>
      ) : (
        <Text color={COLORS.dim}>Ready</Text>
      )}
    </>
  );
}

interface TranscriptLinePayload {
  color: string;
  dim?: boolean;
  hitId?: string;
}

type TranscriptDisplayLine = RenderedTranscriptLine<TranscriptLinePayload>;

function buildTranscriptLines(options: {
  items: TranscriptItem[];
  streams: StreamingItem[];
  expandedIds: Record<string, boolean>;
  width: number;
}): TranscriptDisplayLine[] {
  const lines: TranscriptDisplayLine[] = [];
  const contentWidth = Math.max(1, options.width);

  options.items.forEach((item, index) => {
    appendTranscriptGap(lines, item, options.items[index - 1]);
    appendTranscriptItemLines(lines, item, Boolean(options.expandedIds[item.id]), contentWidth);
  });

  options.streams.forEach((stream) => {
    appendWrappedTranscriptLine(lines, {
      sourceId: stream.id,
      text: "Assistant",
      width: contentWidth,
      payload: { color: COLORS.text },
    });
    appendBodyRows(lines, stream.id, stream.content, contentWidth, COLORS.text, false);
  });

  return lines;
}

function appendTranscriptGap(
  lines: TranscriptDisplayLine[],
  item: TranscriptItem,
  previousItem: TranscriptItem | undefined,
): void {
  const gap = transcriptGap(previousItem, item);
  for (let index = 0; index < gap; index += 1) {
    lines.push({
      id: `${item.id}-gap-${index}`,
      sourceId: item.id,
      text: "",
      payload: { color: COLORS.text },
    });
  }
}

function appendTranscriptItemLines(
  lines: TranscriptDisplayLine[],
  item: TranscriptItem,
  expanded: boolean,
  width: number,
): void {
  const meta = transcriptMeta(item);
  const isInternal = transcriptGroup(item) === "internal";
  const hitId = item.collapsible ? item.id : undefined;

  if (item.collapsible && !expanded) {
    appendWrappedTranscriptLine(lines, {
      sourceId: item.id,
      text: collapsedTranscriptText(item, meta.label),
      width,
      payload: { color: meta.bodyColor, dim: isInternal, hitId },
    });
    return;
  }

  appendExpandedTranscriptLines(lines, item, expanded, width, meta, isInternal, hitId);
}

function collapsedTranscriptText(item: TranscriptItem, label: string): string {
  const preview = transcriptPreview(item, false);
  const prefix = label ? `${compactLine(label, COMPACT_LABEL_LENGTH)}: ` : "";
  return `${prefix}${preview} show more`;
}

function appendExpandedTranscriptLines(
  lines: TranscriptDisplayLine[],
  item: TranscriptItem,
  expanded: boolean,
  width: number,
  meta: ReturnType<typeof transcriptMeta>,
  isInternal: boolean,
  hitId?: string,
): void {
  const compactItem = isCompactTranscriptItem(item);
  const body = transcriptBodyForDisplay(item, expanded);
  const label = compactLine(meta.label, COMPACT_LABEL_LENGTH);
  const bodyPrefix = item.kind === "tool_output" ? `${toolOutputName(item.title)} ` : "";

  if (compactItem && body.trim() && !body.includes("\n")) {
    appendWrappedTranscriptLine(lines, {
      sourceId: item.id,
      text: `${expanded ? "[-] " : ""}${label}: ${bodyPrefix}${compactLine(body, COMPACT_BODY_LENGTH)}`,
      width,
      payload: { color: meta.bodyColor, dim: isInternal, hitId },
    });
    return;
  }

  appendWrappedTranscriptLine(lines, {
    sourceId: item.id,
    text: `${expanded ? "[-] " : ""}${label}${item.collapsible ? " collapse" : ""}`,
    width,
    payload: { color: meta.labelColor, dim: isInternal, hitId },
  });

  if (bodyPrefix) {
    appendWrappedTranscriptLine(lines, {
      sourceId: item.id,
      text: `  ${bodyPrefix}`,
      width,
      payload: { color: meta.bodyColor, dim: compactItem },
    });
  }

  appendBodyRows(lines, item.id, body, width, meta.bodyColor, compactItem);
}

function transcriptBodyForDisplay(item: TranscriptItem, expanded: boolean): string {
  if (!item.collapsible) return item.body;
  return expanded ? item.body : transcriptPreview(item, false);
}

function appendBodyRows(
  lines: TranscriptDisplayLine[],
  sourceId: string,
  body: string,
  width: number,
  color: string,
  dim: boolean,
): void {
  if (!body.trim()) return;

  markdownDisplayRows(body, width - 2).forEach((line) => {
    appendWrappedTranscriptLine(lines, {
      sourceId,
      text: `  ${line}`,
      width,
      payload: { color, dim },
    });
  });
}

function appendWrappedTranscriptLine(
  lines: TranscriptDisplayLine[],
  options: {
    sourceId: string;
    text: string;
    width: number;
    payload: TranscriptLinePayload;
  },
): void {
  wrapTextToRows(options.text, options.width).forEach((row, index) => {
    lines.push({
      id: `${options.sourceId}-${lines.length}-${index}`,
      sourceId: options.sourceId,
      text: row,
      payload: index === 0 ? options.payload : { ...options.payload, hitId: undefined },
    });
  });
}

function buildTranscriptHitAreas(
  visibleLines: TranscriptDisplayLine[],
): TranscriptHitArea[] {
  return visibleLines
    .map((line, index) => {
      if (!line.payload.hitId) return null;
      return {
        id: line.payload.hitId,
        row: TRANSCRIPT_FIRST_CONTENT_ROW + index,
        startColumn: TRANSCRIPT_CONTENT_COLUMN,
        endColumn: Number.MAX_SAFE_INTEGER,
      };
    })
    .filter((area): area is TranscriptHitArea => Boolean(area));
}

function scrollActionFromKey(key: {
  pageUp: boolean;
  pageDown: boolean;
  upArrow: boolean;
  downArrow: boolean;
  shift: boolean;
  meta: boolean;
}): ScrollAction | null {
  if (key.pageUp) return { type: "page_up" };
  if (key.pageDown) return { type: "page_down" };
  if (key.meta && key.upArrow) return { type: "home" };
  if (key.meta && key.downArrow) return { type: "end" };
  if (key.shift && key.upArrow) return { type: "line_up" };
  if (key.shift && key.downArrow) return { type: "line_down" };
  return null;
}

function useSmoothScrollOffset(totalRows: number, viewportRows: number) {
  const [scrollOffset, setScrollOffset] = useState(0);
  const targetOffset = useRef(0);
  const previousTotalRows = useRef(0);
  const totalRowsRef = useRef(totalRows);
  const viewportRowsRef = useRef(viewportRows);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  totalRowsRef.current = totalRows;
  viewportRowsRef.current = viewportRows;

  const stopScrollTimer = () => {
    if (!timer.current) return;
    clearInterval(timer.current);
    timer.current = null;
  };

  const animateTowardTarget = () => {
    if (timer.current) return;
    timer.current = setInterval(() => {
      setScrollOffset((current) => {
        const next = nextSmoothScrollOffset({
          currentOffset: current,
          targetOffset: targetOffset.current,
          totalRows: totalRowsRef.current,
          viewportRows: viewportRowsRef.current,
        });
        if (next === targetOffset.current) stopScrollTimer();
        return next;
      });
    }, TRANSCRIPT_SMOOTH_SCROLL_FRAME_MS);
  };

  const moveByAction = (action: ScrollAction) => {
    targetOffset.current = applyScrollAction(
      targetOffset.current,
      action,
      totalRowsRef.current,
      viewportRowsRef.current,
    );
    animateTowardTarget();
  };

  useEffect(() => {
    setScrollOffset((current) => {
      const nextCurrent = keepScrollPositionAfterRowChange({
        previousOffset: current,
        previousTotalRows: previousTotalRows.current,
        nextTotalRows: totalRows,
        viewportRows,
      });
      targetOffset.current = keepScrollPositionAfterRowChange({
        previousOffset: targetOffset.current,
        previousTotalRows: previousTotalRows.current,
        nextTotalRows: totalRows,
        viewportRows,
      });
      previousTotalRows.current = totalRows;
      return nextCurrent;
    });
  }, [totalRows, viewportRows]);

  useEffect(() => () => stopScrollTimer(), []);

  return { scrollOffset, moveByAction };
}

function Transcript({
  lines,
  setExpandedIds,
  height,
  mouseActive,
  top,
  left,
  width,
}: {
  lines: TranscriptDisplayLine[];
  setExpandedIds: Dispatch<SetStateAction<Record<string, boolean>>>;
  height: number;
  mouseActive: boolean;
  top: number;
  left: number;
  width: number;
}) {
  const contentRows = Math.max(1, height - TRANSCRIPT_CHROME_ROWS);
  const { scrollOffset, moveByAction } = useSmoothScrollOffset(lines.length, contentRows);
  const viewport = createViewportWindow(lines, contentRows, scrollOffset);
  const visibleLines = viewport.lines;
  const hitAreas = buildTranscriptHitAreas(visibleLines);

  useInput((input, key) => {
    if (!isSgrMouseInput(input)) {
      const action = scrollActionFromKey(key);
      if (!action) return;
      moveByAction(action);
      return;
    }

    if (isSgrMouseInput(input)) {
      if (!mouseActive) return;
      const wheels = parseSgrMouseWheels(input)
        .filter((wheel) => isMouseWithinBounds(wheel, { top, left, width, height }));
      if (wheels.length > 0) {
        wheels.forEach((wheel) => {
          moveByAction({
            type: wheel.direction === "up" ? "line_up" : "line_down",
            rows: TRANSCRIPT_WHEEL_ROWS,
          });
        });
        return;
      }

      const click = parseSgrMouseClick(input);
      if (!click) return;
      if (!isMouseWithinBounds(click, { top, left, width, height })) return;

      const itemId = findTranscriptMouseHit({
        click,
        transcriptTop: top,
        transcriptLeft: left,
        hitAreas,
      });
      if (!itemId) return;

      setExpandedIds((current) => ({ ...current, [itemId]: !current[itemId] }));
      return;
    }
  });

  return (
    <Box
      flexDirection="column"
      width={width}
      height={height}
      borderStyle="round"
      borderColor={COLORS.border}
      paddingX={1}
    >
      {visibleLines.map((line) => (
        <Text
          key={line.id}
          color={line.payload.color}
          dimColor={line.payload.dim}
          wrap="truncate"
        >
          {line.text ? (
            <MarkdownInline text={line.text} color={line.payload.color} />
          ) : (
            " "
          )}
        </Text>
      ))}
    </Box>
  );
}

function workerStatusColor(status: string): string {
  if (status === "completed") return COLORS.success;
  if (status === "failed") return COLORS.danger;
  if (status === "stopped") return COLORS.accent;
  return COLORS.info;
}

function workerRoleColor(role: string): string {
  if (role === "implementer") return COLORS.accent;
  if (role === "verifier") return COLORS.success;
  if (role === "summarizer") return COLORS.info;
  if (role === "explorer") return "#b48ead";
  return COLORS.text;
}

function workerStatusMark(status: string): string {
  if (status === "running") return "*";
  if (status === "completed") return "✓";
  if (status === "failed") return "x";
  if (status === "stopped") return "■";
  return "○";
}

function workerActivityColor(activity: WorkerActivityItem): string {
  if (activity.type === "tool_call") return COLORS.info;
  if (activity.type === "tool_output") return COLORS.dim;
  if (activity.type === "notification") return COLORS.text;
  if (activity.type === "status") return workerStatusColor(activity.title.split(/\s+/).at(-1) ?? "");
  return COLORS.dim;
}

function workerActivityMarkerColor(activity: WorkerActivityItem): string {
  if (activity.type === "tool_call") return COLORS.accent;
  return workerActivityColor(activity);
}

function workerResultMarker(result: WorkerResultLine): string {
  if (result.kind === "summary") return "✓";
  if (result.kind === "section") return "─";
  if (result.kind === "risk") return "!";
  if (result.kind === "next") return ">";
  if (result.kind === "continuation") return " ";
  return "•";
}

function workerResultColor(result: WorkerResultLine, status: string): string {
  if (result.kind === "section" || result.kind === "item" || result.kind === "continuation") return COLORS.dim;
  if (result.kind === "risk") return COLORS.danger;
  if (result.kind === "next") return COLORS.info;
  if (result.kind === "fallback") return workerStatusColor(status);
  return COLORS.text;
}

function workerResultMarkerColor(result: WorkerResultLine, status: string): string {
  if (result.kind === "section") return COLORS.border;
  if (result.kind === "risk") return COLORS.danger;
  if (result.kind === "next") return COLORS.accent;
  if (result.kind === "summary") return workerStatusColor(status);
  return COLORS.dim;
}

function WorkerPaneBodyRow({
  row,
  width,
}: {
  row: WorkerPaneRow;
  width: number;
}) {
  if (row.type === "blank") return <Text> </Text>;
  if (row.type === "waiting") return <Text color={COLORS.dim}>{row.text}</Text>;
  if (row.type === "result_separator") {
    return <Text color={COLORS.border} wrap="truncate">{compactLine(` ${"─".repeat(Math.max(0, width - 1))}`, width)}</Text>;
  }
  if (row.type === "result") {
    const marker = workerResultMarker(row.result);
    const text = compactLine(row.result.text, Math.max(1, width - 4));
    return (
      <Text wrap="truncate">
        <Text color={workerResultMarkerColor(row.result, row.status)}>{` ${marker} `}</Text>
        <Text color={workerResultColor(row.result, row.status)}>{text}</Text>
      </Text>
    );
  }

  const labelWidth = Math.min(14, Math.max(0, width - 6));
  const label = compactLine(row.line.label, labelWidth).padEnd(labelWidth);
  const prefix = ` ${row.line.marker} `;
  const detail = row.line.detail ? ` ${row.line.detail}` : "";
  const availableDetailWidth = Math.max(0, width - prefix.length - label.length);
  const displayedDetail = availableDetailWidth > 1 ? compactLine(detail, availableDetailWidth) : "";

  return (
    <Text wrap="truncate">
      <Text color={workerActivityMarkerColor(row.line.activity)}>{prefix}</Text>
      <Text color={workerActivityColor(row.line.activity)}>{label}</Text>
      <Text color={COLORS.dim}>{displayedDetail}</Text>
    </Text>
  );
}

function WorkerPaneHeader({
  worker,
  width,
}: {
  worker: WorkerState;
  width: number;
}) {
  const prefix = " ";
  const suffix = worker.status;
  const role = worker.role && worker.role !== "worker" ? worker.role : "";
  const roleText = role ? `[${compactLine(role, 12)}] ` : "";
  const titleWidth = Math.max(8, width - prefix.length - suffix.length - roleText.length - 5);
  const title = compactLine(worker.title, titleWidth);
  const lineLength = prefix.length + 2 + roleText.length + title.length + suffix.length + 1;
  const spacer = lineLength < width ? " " : "";

  return (
    <Text wrap="truncate">
      <Text color={workerStatusColor(worker.status)}>{`${prefix}${workerStatusMark(worker.status)} `}</Text>
      {roleText ? <Text color={workerRoleColor(worker.role)}>{roleText}</Text> : null}
      <Text color={COLORS.text}>{title}</Text>
      <Text>{spacer}</Text>
      <Text color={workerStatusColor(worker.status)}>{suffix}</Text>
    </Text>
  );
}

function WorkerPaneBody({
  worker,
  width,
  height,
}: {
  worker: WorkerState;
  width: number;
  height: number;
}) {
  const bodyRows = Math.max(0, height - 1);
  const rows = buildWorkerPaneRows(worker, width, bodyRows);

  return (
    <>
      {rows.map((row, index) => (
        <WorkerPaneBodyRow
          key={`${worker.id}-body-${index}`}
          row={row}
          width={Math.max(24, width)}
        />
      ))}
    </>
  );
}

function WorkerPane({
  worker,
  width,
  height,
}: {
  worker: WorkerState;
  width: number;
  height: number;
}) {
  const innerWidth = Math.max(10, width);

  return (
    <Box
      flexDirection="column"
      width={width}
      height={height}
    >
      <WorkerPaneHeader worker={worker} width={innerWidth} />
      <WorkerPaneBody
        worker={worker}
        width={innerWidth}
        height={height}
      />
    </Box>
  );
}

const MemoWorkerPane = memo(
  WorkerPane,
  (previous, next) =>
    previous.worker === next.worker &&
    previous.width === next.width &&
    previous.height === next.height,
);

export function workerPaneHeights(totalHeight: number, workerCount: number): number[] {
  if (workerCount <= 0) return [];
  const separatorRows = workerSeparatorCount(totalHeight, workerCount);
  const contentRows = Math.max(0, totalHeight - separatorRows);
  const baseHeight = Math.floor(contentRows / workerCount);
  const extraRows = contentRows % workerCount;

  return Array.from(
    { length: workerCount },
    (_, index) => baseHeight + (index < extraRows ? 1 : 0),
  );
}

export function workerSeparatorCount(totalHeight: number, workerCount: number): number {
  if (workerCount <= 1) return 0;
  return Math.min(workerCount - 1, Math.max(0, totalHeight - workerCount));
}

export function shouldRenderWorkerSeparator(
  workerIndex: number,
  workerCount: number,
  separatorCount = Math.max(0, workerCount - 1),
): boolean {
  return workerIndex >= 0 && workerIndex < workerCount - 1 && workerIndex < separatorCount;
}

function todoStatusIcon(status: string): string {
  if (status === "completed") return "✓";
  if (status === "in_progress") return "→";
  return "○";
}

function todoStatusColor(status: string): string {
  if (status === "completed") return COLORS.success;
  if (status === "in_progress") return COLORS.accent;
  return COLORS.dim;
}

function TodoPanel({ todos, width }: { todos: TodoItem[]; width: number }) {
  if (todos.length === 0) return null;
  const innerWidth = Math.max(10, width - 4);
  const title = `Tasks (${todos.length})`;
  return (
    <Box
      flexDirection="column"
      width={width}
      borderStyle="round"
      borderColor={COLORS.border}
      paddingX={1}
    >
      <Text color={COLORS.accent} wrap="truncate">
        {compactLine(title, innerWidth)}
      </Text>
      {todos.map((todo, index) => (
        <Text key={`${todo.task}-${index}`} wrap="truncate">
          <Text color={todoStatusColor(todo.status)}>{`${todoStatusIcon(todo.status)} `}</Text>
          <Text color={COLORS.text}>{compactLine(todo.task, Math.max(1, innerWidth - 2))}</Text>
        </Text>
      ))}
    </Box>
  );
}

function WorkerPanes({
  workers,
  layout,
  height,
}: {
  workers: WorkerState[];
  layout: WorkerPaneLayout;
  height: number;
}) {
  if (workers.length === 0) return null;

  const innerWidth = Math.max(24, layout.paneWidth - 4);
  const innerHeight = Math.max(1, height - 3);
  const paneHeights = workerPaneHeights(innerHeight, workers.length);
  const separatorCount = workerSeparatorCount(innerHeight, workers.length);
  const runningCount = workers.filter((worker) => worker.status === "running").length;
  const separator = compactLine("─".repeat(innerWidth), innerWidth);

  return (
    <Box
      flexDirection="column"
      width={layout.paneWidth}
      height={height}
      borderStyle="round"
      borderColor={runningCount ? COLORS.info : COLORS.border}
      paddingX={1}
    >
      <Text color={COLORS.accent} wrap="truncate">
        {compactLine(`Workers ${workers.length}${runningCount ? `  ${runningCount} running` : ""}`, innerWidth)}
      </Text>
      {workers.map((worker, index) => {
        return (
          <Fragment key={worker.id}>
            <MemoWorkerPane
              worker={worker}
              width={innerWidth}
              height={paneHeights[index] ?? 0}
            />
            {shouldRenderWorkerSeparator(index, workers.length, separatorCount) ? (
              <Text color={COLORS.border} wrap="truncate">{separator}</Text>
            ) : null}
          </Fragment>
        );
      })}
    </Box>
  );
}

function SectionCard({
  title,
  children,
  width,
}: {
  title: string;
  children: React.ReactNode;
  width?: number;
}) {
  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={COLORS.borderMuted}
      paddingX={1}
      width={width}
    >
      <Text color={COLORS.accent} wrap="truncate">{title}</Text>
      {children}
    </Box>
  );
}

function commandAvailable(command: string, availableCommands: Set<string>): boolean {
  return availableCommands.has(command);
}

function formatCommandGroup(
  commands: string[],
  availableCommands: Set<string>,
  width: number,
): string {
  const visibleCommands = commands.filter((command) => commandAvailable(command, availableCommands));
  return compactLine(visibleCommands.join("  "), width);
}

function WelcomePanel({
  cwd,
  commands,
  width,
}: {
  cwd: string;
  commands: CommandOption[];
  width: number;
}) {
  const availableCommands = new Set(commands.map((c) => c.name));
  const panelWidth = Math.max(1, width);
  const innerWidth = Math.max(1, panelWidth - 4);
  const workspaceLabel = truncateMiddle(homeCompressed(cwd), Math.max(18, innerWidth - 12));
  const planningCommands = formatCommandGroup(["/plan", "/mode", "/skills"], availableCommands, innerWidth - 9);
  const setupCommands = formatCommandGroup(["/models", "/connect"], availableCommands, innerWidth - 7);
  const contextCommands = formatCommandGroup(["/context", "/compact", "/help"], availableCommands, innerWidth - 9);

  return (
    <SectionCard title="Workspace ready" width={panelWidth}>
      <Text wrap="truncate">
        <Text color={COLORS.muted}>cwd </Text>
        <Text color={COLORS.text}>{workspaceLabel}</Text>
      </Text>
      <Text wrap="truncate">
        <Text color={COLORS.accent}>Plan </Text>
        <Text color={COLORS.dim}>{planningCommands || "type a task directly"}</Text>
      </Text>
      <Text wrap="truncate">
        <Text color={COLORS.accent}>Setup </Text>
        <Text color={COLORS.dim}>{setupCommands || "provider and model configured"}</Text>
      </Text>
      <Text wrap="truncate">
        <Text color={COLORS.accent}>State </Text>
        <Text color={COLORS.dim}>{contextCommands || "conversation controls unavailable"}</Text>
      </Text>
    </SectionCard>
  );
}

function Banner({ logo, subtitle, width }: { logo: string[]; subtitle?: string; width: number }) {
  const useWideBanner = shouldUseWideBanner(width);
  const tagline = subtitle === "Your coding sidekick"
    ? "AI development cockpit for terminal-first engineering"
    : subtitle;

  if (!useWideBanner) {
    const innerWidth = Math.max(18, width - 4);
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Text color={COLORS.accent} bold wrap="truncate">
          {compactLine("TERMINUS", innerWidth)}
        </Text>
        <Text color={COLORS.dim} wrap="truncate">
          {compactLine("agentic engineering in your terminal", innerWidth)}
        </Text>
        <Text color={COLORS.dim} wrap="truncate">
          {compactLine(tagline ?? "", innerWidth)}
        </Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginBottom={1}>
      {logo.map((line, index) => (
        <Text key={`${line}-${index}`} color={index === 0 ? COLORS.info : COLORS.accent}>
          {truncatePreservingWhitespace(line, width)}
        </Text>
      ))}
      {tagline ? (
        <Text color={COLORS.dim} wrap="truncate">
          {compactLine(tagline, Math.max(1, width))}
        </Text>
      ) : null}
    </Box>
  );
}

function SelectionModal<T extends { name: string; description?: string; loaded?: boolean }>({
  title,
  subtitle,
  options,
  onSelect,
}: {
  title: string;
  subtitle: string;
  options: T[];
  onSelect: (name: string | null) => void;
}) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const optionRange = visibleOptionRange(options.length, selectedIndex, MODAL_OPTION_ROWS);
  const visibleOptions = options.slice(optionRange.start, optionRange.end);

  useInput((input, key) => {
    if (key.escape) {
      onSelect(null);
      return;
    }
    if (key.pageUp) {
      setSelectedIndex((current) => Math.max(0, current - MODAL_OPTION_ROWS));
      return;
    }
    if (key.pageDown) {
      setSelectedIndex((current) => Math.min(options.length - 1, current + MODAL_OPTION_ROWS));
      return;
    }
    if (key.upArrow) {
      setSelectedIndex((current) => Math.max(0, current - 1));
      return;
    }
    if (key.downArrow) {
      setSelectedIndex((current) => Math.min(options.length - 1, current + 1));
      return;
    }
    if (key.return) {
      onSelect(options[selectedIndex]?.name ?? null);
      return;
    }
    if (!key.ctrl && !key.meta && input >= "1" && input <= "9") {
      const index = Number(input) - 1;
      if (index < options.length) {
        onSelect(options[index].name);
      }
    }
  });

  return (
    <Box flexDirection="column" borderStyle="double" borderColor={COLORS.accent} paddingX={1}>
      <Text color={COLORS.accent}>{title}</Text>
      <Text color={COLORS.dim}>{subtitle}</Text>
      {visibleOptions.map((option, visibleIndex) => {
        const index = optionRange.start + visibleIndex;
        return (
        <Text
          key={option.name}
          color={index === selectedIndex ? COLORS.background : COLORS.text}
          backgroundColor={index === selectedIndex ? COLORS.accent : undefined}
        >
          {`${index + 1}. ${option.name}${option.loaded ? " [loaded]" : ""}${option.description ? ` - ${option.description}` : ""}`}
        </Text>
        );
      })}
      <Text color={COLORS.dim}>
        {`Enter choose  Esc cancel${options.length > MODAL_OPTION_ROWS ? `  ${optionRange.start + 1}-${optionRange.end}/${options.length}` : ""}`}
      </Text>
    </Box>
  );
}

function QuestionModal({
  questions,
  onSubmit,
}: {
  questions: GuidedQuestion[];
  onSubmit: (content: string) => void;
}) {
  const usesReviewStep = shouldUseQuestionReview(questions);
  const reviewSubmitIndex = questions.length;
  const [questionIndex, setQuestionIndex] = useState(0);
  const [optionIndex, setOptionIndex] = useState(0);
  const [phase, setPhase] = useState<"answering" | "reviewing">("answering");
  const [reviewIndex, setReviewIndex] = useState(0);
  const [editingFromReview, setEditingFromReview] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [notes, setNotes] = useState(() => questions.map(() => ""));
  const [selectedOptions, setSelectedOptions] = useState<number[][]>(() => questions.map(() => []));
  const notesRef = useRef(notes);
  const selectedOptionsRef = useRef(selectedOptions);
  const question = questions[questionIndex] ?? {
    text: "Please clarify your preference.",
    options: ["Use the recommended default", "Let me decide manually", "Skip this for now"] as [string, string, string],
    allowMultiple: false,
  };
  const note = notes[questionIndex] ?? "";
  const currentSelections = selectedOptions[questionIndex] ?? [];
  const actionLabel = questionActionLabel(questionIndex, questions.length, usesReviewStep);
  const reviewItems = buildQuestionReviewItems(questions, selectedOptions, notes);
  const isReviewing = phase === "reviewing";

  useEffect(() => {
    setCursor((notes[questionIndex] ?? "").length);
  }, [notes, questionIndex]);

  useEffect(() => {
    notesRef.current = notes;
  }, [notes]);

  useEffect(() => {
    selectedOptionsRef.current = selectedOptions;
  }, [selectedOptions]);

  useInput((input, key) => {
    if (isSgrMouseInput(input)) return;
    if (key.escape) {
      onSubmit("");
      return;
    }
    if (isReviewing) {
      if (key.upArrow) {
        setReviewIndex((current) => previousCyclicIndex(current, reviewSubmitIndex + 1));
        return;
      }
      if (key.downArrow) {
        setReviewIndex((current) => nextCyclicIndex(current, reviewSubmitIndex + 1));
        return;
      }
      if (input >= "1" && input <= "9") {
        setReviewIndex(Math.min(reviewSubmitIndex, Number(input) - 1));
        return;
      }
      if (key.return) {
        if (reviewIndex === reviewSubmitIndex) {
          onSubmit(buildQuestionAnswerSummary(questions, selectedOptionsRef.current, notesRef.current));
          return;
        }
        startEditingQuestion({
          nextQuestionIndex: reviewIndex,
          selectedOptions: selectedOptionsRef.current,
          setPhase,
          setQuestionIndex,
          setOptionIndex,
          setInputFocused,
          setEditingFromReview,
        });
      }
      return;
    }
    if (input === "\t") {
      setInputFocused((current) => !current);
      return;
    }
    if (key.upArrow) {
      setInputFocused(false);
      setOptionIndex((current) => previousCyclicIndex(current, questionFocusTargetCount(question)));
      return;
    }
    if (key.downArrow) {
      setInputFocused(false);
      setOptionIndex((current) => nextCyclicIndex(current, questionFocusTargetCount(question)));
      return;
    }
    if (!inputFocused && key.leftArrow) {
      moveToQuestion({
        nextQuestionIndex: previousCyclicIndex(questionIndex, questions.length),
        selectedOptions: selectedOptionsRef.current,
        setQuestionIndex,
        setOptionIndex,
        setInputFocused,
      });
      return;
    }
    if (!inputFocused && key.rightArrow) {
      moveToQuestion({
        nextQuestionIndex: nextCyclicIndex(questionIndex, questions.length),
        selectedOptions: selectedOptionsRef.current,
        setQuestionIndex,
        setOptionIndex,
        setInputFocused,
      });
      return;
    }
    if (inputFocused && key.leftArrow) {
      setCursor((current) => Math.max(0, current - 1));
      return;
    }
    if (inputFocused && key.rightArrow) {
      setCursor((current) => Math.min(note.length, current + 1));
      return;
    }
    if (inputFocused && (key.backspace || key.delete)) {
      deleteQuestionNoteCharacter(questionIndex, cursor, notesRef, setNotes, setCursor);
      return;
    }
    if (key.return) {
      if (inputFocused) {
        setInputFocused(false);
        setOptionIndex(questionSubmitIndex(question));
        return;
      }
      if (optionIndex !== questionSubmitIndex(question)) {
        toggleQuestionOption(questionIndex, optionIndex, question.allowMultiple, selectedOptionsRef, setSelectedOptions);
        return;
      }
      applyQuestionAdvanceResult({
        result: getQuestionAdvanceResult({
          questionIndex,
          questions,
          notes: notesRef.current,
          selectedOptions: selectedOptionsRef.current,
        }),
        questionIndex,
        editingFromReview,
        selectedOptions: selectedOptionsRef.current,
        onSubmit,
        setQuestionIndex,
        setOptionIndex,
        setInputFocused,
        setPhase,
        setReviewIndex,
        setEditingFromReview,
      });
      return;
    }
    if (inputFocused && !key.ctrl && !key.meta && input.length > 0) {
      insertQuestionNoteText(questionIndex, input, cursor, notesRef, setNotes, setCursor);
    }
  });

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.accent} paddingX={2} paddingY={1}>
      <Box justifyContent="space-between">
        <Text color={COLORS.accent} bold>
          {isReviewing ? "Review answers" : `Question ${questionIndex + 1}/${questions.length}`}
        </Text>
        <Text color={COLORS.dim}>
          {isReviewing ? "Edit or submit" : question.allowMultiple ? "Multi-select" : "Single choice"}
        </Text>
      </Box>
      {isReviewing ? (
        <ReviewQuestionList reviewItems={reviewItems} reviewIndex={reviewIndex} reviewSubmitIndex={reviewSubmitIndex} />
      ) : (
        <QuestionEditor
          actionLabel={actionLabel}
          cursor={cursor}
          inputFocused={inputFocused}
          note={note}
          optionIndex={optionIndex}
          question={question}
          questionIndex={questionIndex}
          currentSelections={currentSelections}
        />
      )}
    </Box>
  );
}

function QuestionEditor({
  actionLabel,
  cursor,
  currentSelections,
  inputFocused,
  note,
  optionIndex,
  question,
  questionIndex,
}: {
  actionLabel: string;
  cursor: number;
  currentSelections: number[];
  inputFocused: boolean;
  note: string;
  optionIndex: number;
  question: GuidedQuestion;
  questionIndex: number;
}) {
  const actionFocused = !inputFocused && optionIndex === questionSubmitIndex(question);

  return (
    <>
      <Box marginTop={1} marginBottom={1}>
        <Text color={COLORS.text} bold>{question.text}</Text>
      </Box>
      <Box flexDirection="column">
        {question.options.map((option, index) => {
          const selected = currentSelections.includes(index);
          const focused = !inputFocused && index === optionIndex;
          const marker = selected ? "*" : "o";
          return (
            <Box key={`${questionIndex}-${option}`} marginY={0}>
              <Text color={focused ? COLORS.background : selected ? COLORS.accent : COLORS.dim}>
                {focused ? "> " : "  "}
              </Text>
              <Text
                color={focused ? COLORS.background : selected ? COLORS.accent : COLORS.text}
                backgroundColor={focused ? COLORS.accent : undefined}
              >
                {`${marker} ${index + 1}. ${option}`}
              </Text>
            </Box>
          );
        })}
      </Box>
      <Box marginTop={1}>
        <Text color={inputFocused ? COLORS.accent : COLORS.dim}>{"Notes "}</Text>
        <Text color={COLORS.dim}>{"(optional): "}</Text>
        <Text color={COLORS.text}>{note.slice(0, cursor)}</Text>
        <Text color={inputFocused ? COLORS.accent : COLORS.dim}>_</Text>
        <Text color={COLORS.text}>{note.slice(cursor)}</Text>
      </Box>
      <Box marginTop={1}>
        <Text
          color={actionFocused ? COLORS.background : COLORS.text}
          backgroundColor={actionFocused ? COLORS.accent : undefined}
          bold={actionFocused}
        >
          {actionFocused ? "> " : "  "}
        </Text>
        <Text
          color={actionFocused ? COLORS.background : COLORS.text}
          backgroundColor={actionFocused ? COLORS.accent : undefined}
          bold={actionFocused}
        >
          {`  ${actionLabel}  `}
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text color={COLORS.dim}>
          {`Enter ${actionFocused ? "activate button" : question.allowMultiple ? "toggle option" : "select option"}  Up/Down move  Left/Right question  Tab notes  Esc cancel`}
        </Text>
      </Box>
    </>
  );
}

function ReviewQuestionList({
  reviewItems,
  reviewIndex,
  reviewSubmitIndex,
}: {
  reviewItems: QuestionReviewItem[];
  reviewIndex: number;
  reviewSubmitIndex: number;
}) {
  return (
    <>
      <Box marginTop={1} marginBottom={1} flexDirection="column">
        {reviewItems.map((item, index) => {
          const focused = reviewIndex === index;
          return (
            <Box key={`review-${index}`} flexDirection="column" marginBottom={index + REVIEW_SUBMIT_INDEX_OFFSET === reviewItems.length ? 0 : 1}>
              <Text
                color={focused ? COLORS.background : item.complete ? COLORS.text : COLORS.dim}
                backgroundColor={focused ? COLORS.accent : undefined}
                bold={focused}
              >
                {`${focused ? "> " : "  "}${index + 1}. ${item.statusLabel} ${item.question}`}
              </Text>
              <Text color={item.complete ? COLORS.dim : COLORS.danger}>{`     ${item.selectionSummary}`}</Text>
              <Text color={COLORS.dim}>{`     Notes: ${item.noteSummary}`}</Text>
            </Box>
          );
        })}
      </Box>
      <Box marginTop={1}>
        <Text
          color={reviewIndex === reviewSubmitIndex ? COLORS.background : COLORS.text}
          backgroundColor={reviewIndex === reviewSubmitIndex ? COLORS.accent : undefined}
          bold={reviewIndex === reviewSubmitIndex}
        >
          {`${reviewIndex === reviewSubmitIndex ? "> " : "  "}Submit answers`}
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text color={COLORS.dim}>{"Up/Down move  Enter edit/submit  1-3 jump  Esc cancel"}</Text>
      </Box>
    </>
  );
}

function toggleQuestionOption(
  questionIndex: number,
  optionIndex: number,
  allowMultiple: boolean,
  selectedOptionsRef: MutableRefObject<number[][]>,
  setSelectedOptions: Dispatch<SetStateAction<number[][]>>,
): void {
  const nextOptions = selectedOptionsRef.current.map((selected, index) => {
    if (index !== questionIndex) return selected;
    if (!allowMultiple) return [optionIndex];
    return selected.includes(optionIndex)
      ? selected.filter((candidate) => candidate !== optionIndex)
      : [...selected, optionIndex].sort();
  });
  selectedOptionsRef.current = nextOptions;
  setSelectedOptions(nextOptions);
}

function previousCyclicIndex(current: number, count: number): number {
  if (count <= 0) return 0;
  return (current - 1 + count) % count;
}

function nextCyclicIndex(current: number, count: number): number {
  if (count <= 0) return 0;
  return (current + 1) % count;
}

function questionSubmitIndex(question: GuidedQuestion): number {
  return question.options.length;
}

function questionFocusTargetCount(question: GuidedQuestion): number {
  return question.options.length + 1;
}

function insertQuestionNoteText(
  questionIndex: number,
  input: string,
  cursor: number,
  notesRef: MutableRefObject<string[]>,
  setNotes: Dispatch<SetStateAction<string[]>>,
  setCursor: Dispatch<SetStateAction<number>>,
): void {
  const nextNotes = notesRef.current.map((note, index) => (
    index === questionIndex ? note.slice(0, cursor) + input + note.slice(cursor) : note
  ));
  notesRef.current = nextNotes;
  setNotes(nextNotes);
  setCursor((current) => current + input.length);
}

function deleteQuestionNoteCharacter(
  questionIndex: number,
  cursor: number,
  notesRef: MutableRefObject<string[]>,
  setNotes: Dispatch<SetStateAction<string[]>>,
  setCursor: Dispatch<SetStateAction<number>>,
): void {
  if (cursor === 0) return;
  const nextNotes = notesRef.current.map((note, index) => (
    index === questionIndex ? note.slice(0, cursor - 1) + note.slice(cursor) : note
  ));
  notesRef.current = nextNotes;
  setNotes(nextNotes);
  setCursor((current) => current - 1);
}

function applyQuestionAdvanceResult(options: {
  result: QuestionAdvanceResult;
  questionIndex: number;
  editingFromReview: boolean;
  selectedOptions: number[][];
  onSubmit: (content: string) => void;
  setQuestionIndex: Dispatch<SetStateAction<number>>;
  setOptionIndex: Dispatch<SetStateAction<number>>;
  setInputFocused: Dispatch<SetStateAction<boolean>>;
  setPhase: Dispatch<SetStateAction<"answering" | "reviewing">>;
  setReviewIndex: Dispatch<SetStateAction<number>>;
  setEditingFromReview: Dispatch<SetStateAction<boolean>>;
}): void {
  if (options.editingFromReview) {
    options.setPhase("reviewing");
    options.setReviewIndex(options.questionIndex);
    options.setInputFocused(false);
    options.setEditingFromReview(false);
    return;
  }
  if (options.result.type === "submit") {
    options.onSubmit(options.result.content);
    return;
  }
  if (options.result.type === "enter_review") {
    options.setPhase("reviewing");
    options.setReviewIndex(0);
    options.setInputFocused(false);
    return;
  }
  options.setQuestionIndex(options.questionIndex + 1);
  options.setOptionIndex(questionOptionIndex(options.selectedOptions, options.questionIndex + 1));
  options.setInputFocused(false);
}

function startEditingQuestion(options: {
  nextQuestionIndex: number;
  selectedOptions: number[][];
  setPhase: Dispatch<SetStateAction<"answering" | "reviewing">>;
  setQuestionIndex: Dispatch<SetStateAction<number>>;
  setOptionIndex: Dispatch<SetStateAction<number>>;
  setInputFocused: Dispatch<SetStateAction<boolean>>;
  setEditingFromReview: Dispatch<SetStateAction<boolean>>;
}): void {
  options.setEditingFromReview(true);
  options.setPhase("answering");
  moveToQuestion(options);
}

function moveToQuestion(options: {
  nextQuestionIndex: number;
  selectedOptions: number[][];
  setQuestionIndex: Dispatch<SetStateAction<number>>;
  setOptionIndex: Dispatch<SetStateAction<number>>;
  setInputFocused: Dispatch<SetStateAction<boolean>>;
}): void {
  options.setQuestionIndex(options.nextQuestionIndex);
  options.setOptionIndex(questionOptionIndex(options.selectedOptions, options.nextQuestionIndex));
  options.setInputFocused(false);
}

export type QuestionAdvanceResult =
  | { type: "next_question" }
  | { type: "enter_review" }
  | { type: "submit"; content: string };

export function getQuestionAdvanceResult(options: {
  questionIndex: number;
  questions: GuidedQuestion[];
  selectedOptions: number[][];
  notes: string[];
}): QuestionAdvanceResult {
  const isLastQuestion = options.questionIndex + 1 === options.questions.length;
  if (!isLastQuestion) return { type: "next_question" };
  if (shouldUseQuestionReview(options.questions)) return { type: "enter_review" };
  return {
    type: "submit",
    content: buildQuestionAnswerSummary(options.questions, options.selectedOptions, options.notes),
  };
}

export function buildQuestionAnswerSummary(
  questions: GuidedQuestion[],
  selectedOptions: number[][],
  notes: string[],
): string {
  const lines = ["Answers to your clarifying questions:", ""];
  questions.forEach((question, index) => {
    const selectedLabels = selectedOptions[index]?.map((optionIndex) => question.options[optionIndex]) ?? [];
    const note = notes[index]?.trim() ?? "";
    lines.push(`${index + 1}. ${question.text}`);
    lines.push(`Selected options: ${selectedLabels.length ? selectedLabels.join(", ") : "None selected"}`);
    lines.push(`Additional input: ${note || "None"}`);
    lines.push("");
  });
  return lines.join("\n").trim();
}

export function shouldUseQuestionReview(questions: GuidedQuestion[]): boolean {
  return questions.length > 1;
}

export function questionActionLabel(
  questionIndex: number,
  questionCount: number,
  usesReviewStep: boolean,
): string {
  const isLastQuestion = questionIndex + 1 === questionCount;
  if (!isLastQuestion) return "Next question";
  return usesReviewStep ? "Review answers" : "Submit answer";
}

function questionOptionIndex(selectedOptions: number[][], questionIndex: number): number {
  return selectedOptions[questionIndex]?.[0] ?? 0;
}

interface QuestionReviewItem {
  question: string;
  statusLabel: "[Done]" | "[Pending]";
  selectionSummary: string;
  noteSummary: string;
  complete: boolean;
}

function buildQuestionReviewItems(
  questions: GuidedQuestion[],
  selectedOptions: number[][],
  notes: string[],
): QuestionReviewItem[] {
  return questions.map((question, index) => {
    const selectedLabels = selectedOptions[index]?.map((optionIndex) => question.options[optionIndex]) ?? [];
    const noteSummary = notes[index]?.trim() || "None";
    const complete = selectedLabels.length > 0;
    return {
      question: question.text,
      statusLabel: complete ? "[Done]" : "[Pending]",
      selectionSummary: selectedLabels.length ? selectedLabels.join(", ") : "No option selected",
      noteSummary,
      complete,
    };
  });
}

function ApiKeyModal({
  provider,
  onSubmit,
}: {
  provider: string;
  onSubmit: (key: string) => void;
}) {
  const [value, setValue] = useState("");
  const [cursor, setCursor] = useState(0);

  useInput((input, key) => {
    if (isSgrMouseInput(input)) return;
    if (key.escape) {
      onSubmit("");
      return;
    }
    if (key.leftArrow) {
      setCursor((current) => Math.max(0, current - 1));
      return;
    }
    if (key.rightArrow) {
      setCursor((current) => Math.min(value.length, current + 1));
      return;
    }
    if (key.backspace || key.delete) {
      if (cursor === 0) return;
      setValue((current) => current.slice(0, cursor - 1) + current.slice(cursor));
      setCursor((current) => current - 1);
      return;
    }
    if (key.return) {
      onSubmit(value);
      return;
    }
    if (!key.ctrl && !key.meta && input.length > 0) {
      setValue((current) => current.slice(0, cursor) + input + current.slice(cursor));
      setCursor((current) => current + input.length);
    }
  });

  return (
    <Box flexDirection="column" borderStyle="double" borderColor={COLORS.accent} paddingX={1}>
      <Text color={COLORS.accent}>{`API key for ${provider}`}</Text>
      <Text color={COLORS.dim}>Input is visible in the terminal.</Text>
      <Box>
        <Text color={COLORS.text}>{value.slice(0, cursor)}</Text>
        <Text color={COLORS.accent}>_</Text>
        <Text color={COLORS.text}>{value.slice(cursor)}</Text>
      </Box>
      <Text color={COLORS.dim}>Enter submit  Esc cancel</Text>
    </Box>
  );
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [expandedTranscriptIds, setExpandedTranscriptIds] = useState<Record<string, boolean>>({});
  const clientRef = useRef<SocketClient | null>(null);
  const { exit } = useApp();
  const { stdout } = useStdout();
  const terminalWidth = stdout?.columns ?? 100;
  const terminalHeight = stdout?.rows ?? 32;
  const bannerRows = state.showIntro
    ? calculateBannerRows(terminalWidth, Boolean(state.banner))
    : 0;
  const welcomeRows = state.showIntro ? WELCOME_ROWS : 0;
  const transcriptTop = 1 + bannerRows + welcomeRows;
  const transcriptLeft = 1;
  const transcriptItems = selectTranscriptItems(state);
  const streams = selectStreamingItems(state);
  const workers = selectWorkers(state);
  const hasTranscript = transcriptItems.length > 0;
  const hasWorkers = workers.length > 0;
  const hasTodos = state.todos.length > 0;
  const todoPanelHeight = hasTodos
    ? Math.min(10, Math.max(3, state.todos.length + 3))
    : 0;
  const workerPaneLayout = calculateWorkerPaneLayout({
    terminalWidth,
    terminalHeight,
    hasWorkers,
    workerCount: workers.length,
  });
  const mainContentRows = calculateMainContentRows({
    terminalHeight,
    bannerRows,
    welcomeRows,
    todoPanelRows: todoPanelHeight,
    isGenerating: state.isGenerating,
  });
  const transcriptContentWidth = Math.max(10, workerPaneLayout.transcriptWidth - TRANSCRIPT_CHROME_COLUMNS);
  const transcriptLines = buildTranscriptLines({
    items: transcriptItems,
    streams,
    expandedIds: expandedTranscriptIds,
    width: transcriptContentWidth,
  });
  const bottomWorkerPaneHeight = workerPaneLayout.placement === "bottom"
    ? calculateBottomWorkerPaneHeight(workerPaneLayout.paneRows, mainContentRows)
    : 0;
  const transcriptHeight = calculateTranscriptFrameHeight({
    mainContentRows,
    renderedTranscriptRows: transcriptLines.length,
    bottomWorkerPaneRows: bottomWorkerPaneHeight,
  });
  const sideWorkerPaneHeight = calculateSideWorkerPaneHeight({
    mainContentRows,
    transcriptHeight,
    maxWorkerPaneRows: MAX_SIDE_WORKER_PANE_ROWS,
  });
  const workerPaneHeight = workerPaneLayout.placement === "side"
    ? sideWorkerPaneHeight
    : bottomWorkerPaneHeight;
  const sideBySideHeight = calculateSideBySideHeight(
    transcriptHeight,
    workerPaneHeight,
    mainContentRows,
  );
  useEffect(() => enableSgrMouseReporting(stdout), [stdout]);

  useEffect(() => {
    const socketPath = process.env.TERMINUS_SOCK;
    if (!socketPath) {
      dispatch({ type: "connection_error", error: "TERMINUS_SOCK not set" });
      return;
    }

    const client = new SocketClient(socketPath, {
      onConnected: () => {
        dispatch({ type: "connected" });
        client.send({ type: "ready" });
      },
      onDisconnected: () => {
        dispatch({ type: "disconnected" });
      },
      onError: (error) => {
        dispatch({ type: "connection_error", error });
      },
      onMessage: (message: InboundEnvelope) => {
        const shouldExit =
          message.type === "exit" ||
          (message.type === "event_batch" && message.events.some((event) => event.type === "exit"));
        if (shouldExit) {
          exit();
          return;
        }
        dispatch({ type: "bridge", message });
      },
    });

    clientRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, [exit]);

  const send = (
    payload: OutboundMessage,
    closeSelection?: "model" | "provider" | "skill" | "apiKey" | "question",
  ) => {
    const client = clientRef.current;
    if (!client) {
      dispatch({ type: "connection_error", error: "Not connected to TERMINUS" });
      return;
    }
    client.send(payload);
    if (payload.type === "input" || (payload.type === "question_answer" && payload.content.trim())) {
      dispatch({ type: "input_sent" });
    }
    if (closeSelection) {
      dispatch({ type: "selection_closed", selection: closeSelection });
    }
  };

  const modal =
    state.modelSelect ? (
      <SelectionModal<ModelOption>
        title={state.modelSelect.title}
        subtitle={state.modelSelect.subtitle}
        options={state.modelSelect.options}
        onSelect={(name) => send({ type: "model_selected", name }, "model")}
      />
    ) : state.providerSelect ? (
      <SelectionModal<ProviderOption>
        title={state.providerSelect.title}
        subtitle={state.providerSelect.subtitle}
        options={state.providerSelect.options}
        onSelect={(name) => send({ type: "provider_selected", name }, "provider")}
      />
    ) : state.skillSelect ? (
      <SelectionModal<SkillOption>
        title={state.skillSelect.title}
        subtitle={state.skillSelect.subtitle}
        options={state.skillSelect.options}
        onSelect={(name) => send({ type: "skill_selected", name }, "skill")}
      />
    ) : state.questionSession ? (
      <QuestionModal
        questions={state.questionSession.questions}
        onSubmit={(content) => send({ type: "question_answer", content }, "question")}
      />
    ) : state.apiKeyPrompt ? (
      <ApiKeyModal
        provider={state.apiKeyPrompt.provider}
        onSubmit={(key) => send({ type: "api_key_submitted", key }, "apiKey")}
      />
    ) : null;
  const modalActive = Boolean(modal);

  useInput((input, key) => {
    if (modal) return;
    if (!state.isGenerating || state.inputActive) return;
    if (key.ctrl && input === "c") {
      send({ type: "interrupt" });
    }
  });

  const transcriptView = transcriptHeight > 0 && (hasTranscript || state.isGenerating || streams.length > 0) ? (
    <Transcript
      lines={transcriptLines}
      setExpandedIds={setExpandedTranscriptIds}
      height={transcriptHeight}
      mouseActive={!modal}
      top={transcriptTop}
      left={transcriptLeft}
      width={workerPaneLayout.transcriptWidth}
    />
  ) : null;

  const workerPanes = hasWorkers ? (
    <WorkerPanes
      workers={workers}
      layout={workerPaneLayout}
      height={workerPaneHeight}
    />
  ) : null;

  const todoPanel = hasTodos ? (
    <TodoPanel todos={state.todos} width={terminalWidth} />
  ) : null;

  return (
    <Box flexDirection="column" width={terminalWidth} height={terminalHeight}>
      {state.showIntro && state.banner ? (
        <Banner logo={state.banner.logo} subtitle={state.banner.subtitle} width={terminalWidth} />
      ) : null}
      {state.showIntro ? (
        <WelcomePanel
          cwd={state.status.cwd}
          commands={state.commands}
          width={terminalWidth}
        />
      ) : null}
      {modalActive ? (
        <Box flexGrow={1} justifyContent="center" paddingX={1}>
          {modal}
        </Box>
      ) : workerPaneLayout.placement === "side" && workerPanes ? (
        <Box flexDirection="row" height={sideBySideHeight}>
          <Box width={workerPaneLayout.transcriptWidth}>{transcriptView}</Box>
          {workerPanes}
        </Box>
      ) : (
        <>
          {transcriptView}
          {workerPanes}
        </>
      )}
      {!modalActive ? todoPanel : null}
      {!modalActive ? (
        <InputPanel
          active={state.inputActive}
          commands={state.commands}
          connectionError={state.connectionError}
          isGenerating={state.isGenerating}
          cwd={state.status.cwd}
          model={state.status.model}
          contextPercent={state.status.contextPercent}
          width={terminalWidth}
          onSubmit={(value) => send({ type: "input", content: value })}
          onInterrupt={() => send({ type: "interrupt" })}
          onCopyLast={() => send({ type: "copy_last_response" })}
        />
      ) : null}
      <Box flexGrow={1} />
    </Box>
  );
}
