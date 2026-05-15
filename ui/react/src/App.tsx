import React, { useEffect, useReducer, useRef, useState } from "react";
import { Box, Text, useApp, useInput, useStdout } from "ink";
import { SocketClient } from "./socket-client.js";
import type {
  CommandOption,
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
} from "./state.js";
import { calculateTranscriptHeight } from "./layout.js";

const COLORS = {
  background: "#0f1115",
  panel: "#1a1e24",
  border: "#4c566a",
  text: "#e5dccf",
  dim: "#8a8f98",
  accent: "#d9a441",
  accentSoft: "#7c5e22",
  danger: "#d26a5c",
  success: "#86b36b",
  info: "#77a7d9",
};

const COMPACT_LABEL_LENGTH = 18;
const COMPACT_BODY_LENGTH = 52;

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

function formatPercent(value: number): string {
  const normalized = Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
  return `${normalized}%`;
}

type InlineToken =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; label: string; url: string };

function compactLine(value: string, maxLength: number): string {
  const singleLine = value.replace(/\s+/g, " ").trim();
  if (singleLine.length <= maxLength) return singleLine;
  return `${singleLine.slice(0, Math.max(0, maxLength - 1))}…`;
}

function formatWorkerTimestamp(timestamp?: number): string {
  if (!timestamp) return "";
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
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

function MarkdownBlock({
  text,
  color,
}: {
  text: string;
  color: string;
}) {
  const lines = text.split("\n");

  return (
    <Box flexDirection="column">
      {lines.map((line, index) => {
        const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
        const bulletMatch = line.match(/^(\s*)[-*]\s+(.*)$/);
        const orderedMatch = line.match(/^(\s*)(\d+)\.\s+(.*)$/);

        if (headingMatch) {
          return (
            <Text key={`line-${index}`} color={COLORS.accent} bold>
              {headingMatch[2]}
            </Text>
          );
        }

        if (bulletMatch) {
          return (
            <Box key={`line-${index}`}>
              <Text color={COLORS.dim}>• </Text>
              <MarkdownInline text={bulletMatch[2]} color={color} />
            </Box>
          );
        }

        if (orderedMatch) {
          return (
            <Box key={`line-${index}`}>
              <Text color={COLORS.dim}>{`${orderedMatch[2]}. `}</Text>
              <MarkdownInline text={orderedMatch[3]} color={color} />
            </Box>
          );
        }

        if (line.trim() === "") {
          return <Text key={`line-${index}`}> </Text>;
        }

        return (
          <Text key={`line-${index}`} color={color}>
            <MarkdownInline text={line} color={color} />
          </Text>
        );
      })}
    </Box>
  );
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

function estimateRows(item: TranscriptItem): number {
  if (item.collapsible || isCompactTranscriptItem(item)) {
    return 1;
  }

  return Math.min(8, Math.max(1, item.body.split("\n").length + 1));
}

function visibleTranscriptItems(items: TranscriptItem[], maxRows: number): TranscriptItem[] {
  const visible: TranscriptItem[] = [];
  let usedRows = 0;

  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    const rows = estimateRows(item);
    if (visible.length > 0 && usedRows + rows > maxRows) {
      break;
    }
    visible.unshift(item);
    usedRows += rows;
  }

  return visible;
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
  focusedPane,
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
  focusedPane: "input" | "transcript" | "workers";
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
          {focusedPane === "transcript"
            ? "Tab focus input  Up/Down select transcript item  Enter/Space toggle item"
            : focusedPane === "workers"
              ? "Tab focus input  Up/Down select worker  Enter open details  Esc close details"
            : "Enter submit  Tab focus transcript  Ctrl+C interrupt"}
        </Text>
      ) : (
        <Text color={COLORS.dim}>Ready</Text>
      )}
    </>
  );
}

function Transcript({
  items,
  streams,
  height,
  interactive,
}: {
  items: TranscriptItem[];
  streams: StreamingItem[];
  height: number;
  interactive: boolean;
}) {
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const [selectedIndex, setSelectedIndex] = useState(0);
  const visibleItems = visibleTranscriptItems(items, Math.max(1, height - streams.length - 2));

  useEffect(() => {
    if (visibleItems.length === 0) {
      setSelectedIndex(0);
      return;
    }
    setSelectedIndex((current) => Math.min(current, visibleItems.length - 1));
  }, [visibleItems.length]);

  useInput((input, key) => {
    if (!interactive || visibleItems.length === 0) return;
    if (key.upArrow) {
      setSelectedIndex((current) => Math.max(0, current - 1));
      return;
    }
    if (key.downArrow) {
      setSelectedIndex((current) => Math.min(visibleItems.length - 1, current + 1));
      return;
    }
    if (key.return || input === " ") {
      const selected = visibleItems[selectedIndex];
      if (!selected?.collapsible) return;
      setExpandedIds((current) => ({ ...current, [selected.id]: !current[selected.id] }));
    }
  });

  return (
    <Box
      flexDirection="column"
      height={height}
      borderStyle="round"
      borderColor={COLORS.border}
      paddingX={1}
    >
      {visibleItems.map((item, index) => (
        <TranscriptRow
          key={item.id}
          item={item}
          expanded={Boolean(expandedIds[item.id])}
          selected={interactive && index === selectedIndex}
          marginTop={transcriptGap(visibleItems[index - 1], item)}
        />
      ))}
      {streams.map((stream) => (
        <Box key={stream.id} marginBottom={1} flexDirection="column">
          <Text color={COLORS.info}>Assistant</Text>
          <MarkdownBlock text={compactLine(stream.content, 2000)} color={COLORS.text} />
        </Box>
      ))}
    </Box>
  );
}

const TranscriptRow = React.memo(function TranscriptRow({
  item,
  expanded,
  selected,
  marginTop,
}: {
  item: TranscriptItem;
  expanded: boolean;
  selected: boolean;
  marginTop: number;
}) {
  const isCollapsible = Boolean(item.collapsible);
  const compactItem = isCompactTranscriptItem(item);
  const isToolCall = item.kind === "tool_call";
  const isToolOutput = item.kind === "tool_output";
  const isInternal = transcriptGroup(item) === "internal";
  const preview = transcriptPreview(item, Boolean(!isCollapsible || expanded));
  const body = isCollapsible && !expanded ? preview : item.body;
  const meta = transcriptMeta(item);
  const label = compactLine(meta.label, COMPACT_LABEL_LENGTH);
  const showMoreLabel = isCollapsible && !expanded ? "show more" : "";
  const labelColor = selected ? COLORS.background : meta.labelColor;
  const bodyColor = selected ? COLORS.background : meta.bodyColor;
  const selectedBackground = selected ? COLORS.accent : undefined;
  const inlineBody = compactItem ? compactLine(body, COMPACT_BODY_LENGTH) : body;
  const renderInline = compactItem && inlineBody.trim() && !inlineBody.includes("\n");
  const bodyPrefix = isToolOutput ? `${toolOutputName(item.title)} ` : "";
  const expandedMarker = isCollapsible ? (expanded ? "[-] " : "") : "";
  const rowMarginBottom = compactItem || isInternal ? 0 : 1;

  if (isCollapsible && !expanded) {
    return (
      <Box marginTop={marginTop} marginBottom={rowMarginBottom} flexDirection="row">
        <Text color={labelColor} backgroundColor={selectedBackground} dimColor={isInternal}>
          {label ? `${label}: ` : ""}
        </Text>
        <Text color={bodyColor} backgroundColor={selectedBackground} dimColor={isInternal}>
          <MarkdownInline text={preview} color={bodyColor} />
        </Text>
        {showMoreLabel ? (
          <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={selectedBackground}>
            {" "}
            {showMoreLabel}
          </Text>
        ) : null}
      </Box>
    );
  }

  if (renderInline) {
    return (
      <Box marginTop={marginTop} marginBottom={rowMarginBottom} flexDirection="row">
        <Text color={labelColor} backgroundColor={selectedBackground} dimColor={isInternal}>
          {expandedMarker}
          {label}:{" "}
        </Text>
        <Text color={bodyColor} backgroundColor={selectedBackground} dimColor={isToolCall || isToolOutput}>
          {bodyPrefix}
          <MarkdownInline text={inlineBody} color={bodyColor} />
        </Text>
      </Box>
    );
  }

  if (!isCollapsible && !compactItem && body.trim() && !body.includes("\n")) {
    return (
      <Box marginTop={marginTop} marginBottom={rowMarginBottom} flexDirection="row">
        <Text color={labelColor} backgroundColor={selectedBackground}>
          {label}:{" "}
        </Text>
        <Text color={bodyColor} backgroundColor={selectedBackground}>
          <MarkdownInline text={body} color={bodyColor} />
        </Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginTop={marginTop} marginBottom={rowMarginBottom}>
      <Box flexDirection="row">
        <Text color={labelColor} backgroundColor={selectedBackground} dimColor={isInternal}>
          {expandedMarker}
          {label}
        </Text>
        {isCollapsible ? (
          <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={selectedBackground}>
            {" "}
            {expanded ? "collapse" : "show more"}
          </Text>
        ) : null}
      </Box>
      {body.trim() ? (
        <Box flexDirection="column" marginLeft={2}>
          {bodyPrefix ? (
            <Text color={bodyColor} backgroundColor={selectedBackground} dimColor={isToolCall || isToolOutput}>
              {bodyPrefix}
            </Text>
          ) : null}
          <MarkdownBlock text={body} color={bodyColor} />
        </Box>
      ) : null}
    </Box>
  );
});

function workerStatusColor(status: string): string {
  if (status === "completed") return COLORS.success;
  if (status === "failed") return COLORS.danger;
  if (status === "stopped") return COLORS.accent;
  return COLORS.info;
}

function formatArgs(args?: Record<string, unknown>): string {
  if (!args) return "";
  try {
    return compactLine(JSON.stringify(args), 140);
  } catch {
    return "";
  }
}

function WorkerActivityRow({
  activity,
  selected,
  width,
}: {
  activity: WorkerActivityItem;
  selected: boolean;
  width: number;
}) {
  const labelColor = selected ? COLORS.background : activity.type === "thinking" ? COLORS.dim : COLORS.info;
  const selectedBackground = selected ? COLORS.accent : undefined;
  const previewWidth = Math.max(16, width - activity.title.length - 24);
  const typeLabel =
    activity.type === "tool_call"
      ? "call"
      : activity.type === "tool_output"
        ? "out"
        : activity.type === "thinking"
          ? "think"
          : activity.type;

  return (
    <Box>
      <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={selectedBackground}>
        {selected ? "> " : "  "}
        {typeLabel.padEnd(5)}
      </Text>
      <Text color={labelColor} backgroundColor={selectedBackground}>
        {compactLine(activity.title, 28)}
      </Text>
      {activity.timestamp ? (
        <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={selectedBackground}>
          {" "}
          {formatWorkerTimestamp(activity.timestamp)}
        </Text>
      ) : null}
      {activity.preview ? (
        <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={selectedBackground}>
          {" "}
          {compactLine(activity.preview, previewWidth)}
        </Text>
      ) : null}
    </Box>
  );
}

function WorkerBoard({
  workers,
  interactive,
  width,
  onExpandedChange,
}: {
  workers: WorkerState[];
  interactive: boolean;
  width: number;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [manualSelection, setManualSelection] = useState(false);
  const [openWorkerId, setOpenWorkerId] = useState<string | null>(null);
  const [selectedActivityIndex, setSelectedActivityIndex] = useState(0);
  const [expandedActivityIds, setExpandedActivityIds] = useState<Record<string, boolean>>({});
  const selectedWorker = workers[Math.min(selectedIndex, workers.length - 1)];
  const openedWorker = openWorkerId
    ? workers.find((worker) => worker.id === openWorkerId) ?? null
    : null;
  const activity = openedWorker
    ? openedWorker.activityOrder
        .map((id) => openedWorker.activityById[id])
        .filter((item): item is WorkerActivityItem => Boolean(item))
        .slice(-6)
    : [];
  const selectedActivity = activity[selectedActivityIndex];

  useEffect(() => {
    setSelectedIndex((current) => Math.min(Math.max(0, current), Math.max(0, workers.length - 1)));
  }, [workers.length]);

  useEffect(() => {
    if (manualSelection) return;
    const newestRunningIndex = workers
      .map((worker, index) => ({ worker, index }))
      .filter(({ worker }) => worker.status === "running")
      .sort((a, b) => (b.worker.lastUpdatedAt ?? 0) - (a.worker.lastUpdatedAt ?? 0))[0]?.index;
    if (newestRunningIndex !== undefined) {
      setSelectedIndex(newestRunningIndex);
    }
  }, [manualSelection, workers]);

  useEffect(() => {
    setSelectedActivityIndex((current) => Math.min(current, Math.max(0, activity.length - 1)));
  }, [activity.length]);

  useEffect(() => {
    onExpandedChange(Boolean(openedWorker));
  }, [onExpandedChange, openedWorker]);

  useInput((input, key) => {
    if (!interactive) return;
    if (key.escape) {
      setOpenWorkerId(null);
      return;
    }
    if (key.leftArrow && openWorkerId) {
      setOpenWorkerId(null);
      return;
    }
    if (key.rightArrow && selectedWorker) {
      setOpenWorkerId(selectedWorker.id);
      return;
    }
    if (key.upArrow) {
      setManualSelection(true);
      setSelectedIndex((current) => Math.max(0, current - 1));
      return;
    }
    if (key.downArrow) {
      setManualSelection(true);
      setSelectedIndex((current) => Math.min(workers.length - 1, current + 1));
      return;
    }
    if (input === "k" && activity.length > 0) {
      setSelectedActivityIndex((current) => Math.max(0, current - 1));
      return;
    }
    if (input === "j" && activity.length > 0) {
      setSelectedActivityIndex((current) => Math.min(activity.length - 1, current + 1));
      return;
    }
    if (input === " " && activity[selectedActivityIndex]) {
      const selectedActivity = activity[selectedActivityIndex];
      setExpandedActivityIds((current) => ({
        ...current,
        [selectedActivity.id]: !current[selectedActivity.id],
      }));
      return;
    }
    if (key.return && selectedWorker) {
      setManualSelection(true);
      setOpenWorkerId((current) => (current === selectedWorker.id ? null : selectedWorker.id));
    }
  });

  if (workers.length === 0) return null;

  const runningCount = workers.filter((worker) => worker.status === "running").length;
  const title = openWorkerId ? "Workers" : `Workers ${workers.length}`;
  const hint = interactive
    ? openWorkerId
      ? "↑↓ worker  j/k activity  Space expand  Esc close"
      : "↑↓ select  Enter details"
    : "Tab focus";
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={interactive ? COLORS.accentSoft : COLORS.border} paddingX={1}>
      <Box>
        <Text color={COLORS.accent}>{title}</Text>
        <Text color={COLORS.dim}>
          {" "}
          {runningCount} running
          {"  "}
          {hint}
        </Text>
      </Box>
      {workers.map((worker, index) => {
        const selected = interactive && index === selectedIndex;
        const backgroundColor = selected ? COLORS.accent : undefined;
        const foreground = selected ? COLORS.background : COLORS.text;
        const countLabel = `${worker.activityCounts.thinking}T ${worker.activityCounts.toolCall}C ${worker.activityCounts.toolOutput}O`;
        const statusMark =
          worker.status === "running"
            ? "●"
            : worker.status === "completed"
              ? "✓"
              : worker.status === "failed"
                ? "×"
                : worker.status === "stopped"
                  ? "■"
                  : "○";
        const availableSummaryWidth = Math.max(0, width - worker.title.length - worker.role.length - countLabel.length - 38);
        const rowSummary = index === selectedIndex ? compactLine(worker.summary || worker.description, availableSummaryWidth) : "";

        return (
          <Box key={worker.id}>
            <Text color={foreground} backgroundColor={backgroundColor}>
              {selected ? ">" : " "} {statusMark} {compactLine(worker.title, 24)}
            </Text>
            <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={backgroundColor}>
              {" "}
              {worker.role}
            </Text>
            <Text color={selected ? COLORS.background : workerStatusColor(worker.status)} backgroundColor={backgroundColor}>
              {" "}
              {worker.status}
            </Text>
            <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={backgroundColor}>
              {" "}
              {countLabel}
            </Text>
            {rowSummary ? (
              <Text color={selected ? COLORS.background : COLORS.dim} backgroundColor={backgroundColor}>
                {" "}
                {rowSummary}
              </Text>
            ) : null}
          </Box>
        );
      })}
      {openedWorker ? (
        <Box flexDirection="column" marginTop={1} paddingX={1}>
          <Box>
            <Text color={COLORS.success}>{openedWorker.title}</Text>
            <Text color={COLORS.dim}>
              {" "}
              detail  {activity.length}/{openedWorker.activityOrder.length} shown
            </Text>
          </Box>
          {activity.length === 0 ? (
            <Text color={COLORS.dim}>No worker activity yet.</Text>
          ) : (
            activity.map((item, index) => (
              <WorkerActivityRow
                key={item.id}
                activity={item}
                selected={interactive && index === selectedActivityIndex}
                width={Math.max(40, width - 6)}
              />
            ))
          )}
          {selectedActivity ? (
            <Box flexDirection="column" marginTop={1}>
              {selectedActivity.type === "tool_call" && formatArgs(selectedActivity.args) ? (
                <Text color={COLORS.dim}>
                  args {compactLine(formatArgs(selectedActivity.args), Math.max(40, width - 10))}
                </Text>
              ) : null}
              {selectedActivity.content || selectedActivity.preview ? (
                <Text color={selectedActivity.type === "tool_output" ? COLORS.dim : COLORS.text}>
                  <MarkdownInline
                    text={compactLine(
                      expandedActivityIds[selectedActivity.id]
                        ? selectedActivity.content || selectedActivity.preview
                        : selectedActivity.preview || selectedActivity.content,
                      expandedActivityIds[selectedActivity.id] ? 900 : Math.max(80, width - 10),
                    )}
                    color={selectedActivity.type === "tool_output" ? COLORS.dim : COLORS.text}
                  />
                </Text>
              ) : null}
            </Box>
          ) : null}
          {openedWorker.result ? (
            <Box marginTop={1}>
              <Text color={workerStatusColor(openedWorker.status)}>
                final {openedWorker.status}:{" "}
              </Text>
              <Text color={COLORS.text}>
                {compactLine(openedWorker.result, Math.max(40, width - 18))}
              </Text>
            </Box>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={COLORS.border} paddingX={1}>
      <Text color={COLORS.accent}>{title}</Text>
      {children}
    </Box>
  );
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
  const suggestions = [
    { command: "/plan", example: "build auth system", label: "Scope a change" },
    { command: "/review", example: "current repo", label: "Audit the repo" },
    { command: "/debug", example: "failing tests", label: "Fix failures" },
    { command: "/mode", example: "coordinator", label: "Use multi-agent flow" },
    { command: "/models", example: "", label: "Switch model" },
    { command: "/context", example: "", label: "Inspect loaded context" },
    { command: "/compact", example: "", label: "Trim conversation state" },
    { command: "/skills", example: "", label: "Load project skills" },
    { command: "/connect", example: "", label: "Configure provider keys" },
  ];

  const recentSessions = [
    "websocket refactor",
    "memory optimization",
    "rag pipeline",
  ];

  const availableCommands = new Set(commands.map((c) => c.name));
  const workspaceLabel = truncateMiddle(homeCompressed(cwd), Math.max(28, width - 18));

  const quickStart = suggestions
    .filter((s) => availableCommands.has(s.command) || s.command === "/debug")
    .slice(0, 3)
    .map((s) => `${s.command}${s.example ? ` ${s.example}` : ""}`)
    .join("   ");

  return (
    <SectionCard title="Welcome">
      <Text color={COLORS.text}>Ready to work in {workspaceLabel}</Text>
      <Text color={COLORS.dim}>Start typing below or use a shortcut like {quickStart}</Text>
      <Text color={COLORS.dim}>Recent: {recentSessions.join("  ·  ")}</Text>
    </SectionCard>
  );
}

function Banner({ logo, subtitle }: { logo: string[]; subtitle?: string }) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      {logo.map((line, index) => (
        <Text key={`${line}-${index}`} color={COLORS.accent}>
          {line}
        </Text>
      ))}
      {subtitle ? <Text color={COLORS.dim}>{subtitle}</Text> : null}
    </Box>
  );
}

function SelectionModal<T extends { name: string; description?: string }>({
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
  useInput((input, key) => {
    if (key.escape) {
      onSelect(null);
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
      {options.map((option, index) => (
        <Text
          key={option.name}
          color={index === selectedIndex ? COLORS.background : COLORS.text}
          backgroundColor={index === selectedIndex ? COLORS.accent : undefined}
        >
          {`${index + 1}. ${option.name}${option.description ? ` - ${option.description}` : ""}`}
        </Text>
      ))}
      <Text color={COLORS.dim}>Enter choose  Esc cancel</Text>
    </Box>
  );
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
  const [focus, setFocus] = useState<"input" | "transcript" | "workers">("input");
  const [workerBoardExpanded, setWorkerBoardExpanded] = useState(false);
  const clientRef = useRef<SocketClient | null>(null);
  const { exit } = useApp();
  const { stdout } = useStdout();
  const terminalWidth = stdout?.columns ?? 100;
  const terminalHeight = stdout?.rows ?? 32;
  const transcriptItems = selectTranscriptItems(state);
  const streams = selectStreamingItems(state);
  const workers = selectWorkers(state);
  const hasTranscript = transcriptItems.length > 0;
  const hasWorkers = workers.length > 0;
  const workersFocused = focus === "workers";
  const transcriptHeight = calculateTranscriptHeight({
    terminalHeight,
    showIntro: state.showIntro,
    hasWorkers,
    workerBoardExpanded,
    isGenerating: state.isGenerating,
  });

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
    closeSelection?: "model" | "provider" | "skill" | "apiKey",
  ) => {
    const client = clientRef.current;
    if (!client) {
      dispatch({ type: "connection_error", error: "Not connected to TERMINUS" });
      return;
    }
    client.send(payload);
    if (payload.type === "input") {
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
    ) : state.apiKeyPrompt ? (
      <ApiKeyModal
        provider={state.apiKeyPrompt.provider}
        onSubmit={(key) => send({ type: "api_key_submitted", key }, "apiKey")}
      />
    ) : null;

  useInput((input, key) => {
    if (modal) return;
    if (key.tab) {
      if (state.inputActive) {
        const focusable: Array<"input" | "transcript" | "workers"> = ["input"];
        if (transcriptItems.length > 0) focusable.push("transcript");
        if (hasWorkers) focusable.push("workers");
        setFocus((current) => {
          const currentIndex = Math.max(0, focusable.indexOf(current));
          return focusable[(currentIndex + 1) % focusable.length] ?? "input";
        });
        return;
      }
      const focusable: Array<"transcript" | "workers"> = [];
      if (transcriptItems.length > 0) focusable.push("transcript");
      if (hasWorkers) focusable.push("workers");
      if (focusable.length > 0) {
        setFocus((current) => {
          const currentIndex = Math.max(0, focusable.indexOf(current as "transcript" | "workers"));
          return focusable[(currentIndex + 1) % focusable.length] ?? "transcript";
        });
      }
      return;
    }
    if (!state.isGenerating || state.inputActive) return;
    if (key.ctrl && input === "c") {
      send({ type: "interrupt" });
    }
  });

  useEffect(() => {
    if (state.inputActive) {
      setFocus("input");
      return;
    }
    if (hasWorkers) {
      setFocus("workers");
      return;
    }
    setFocus("transcript");
  }, [hasWorkers, state.inputActive]);

  useEffect(() => {
    if (!hasWorkers) {
      setWorkerBoardExpanded(false);
    }
  }, [hasWorkers]);

  return (
    <Box flexDirection="column">
      {state.showIntro && state.banner ? (
        <Banner logo={state.banner.logo} subtitle={state.banner.subtitle} />
      ) : null}
      {state.showIntro ? (
        <WelcomePanel
          cwd={state.status.cwd}
          commands={state.commands}
          width={terminalWidth}
        />
      ) : null}
      {(hasTranscript || state.isGenerating || streams.length > 0) ? (
        <Transcript
          items={transcriptItems}
          streams={streams}
          height={transcriptHeight}
          interactive={focus === "transcript" && !modal}
        />
      ) : null}
      <WorkerBoard
        workers={workers}
        interactive={workersFocused && !modal}
        width={terminalWidth}
        onExpandedChange={setWorkerBoardExpanded}
      />
      {modal}
      <InputPanel
        active={state.inputActive && !modal}
        commands={state.commands}
        connectionError={state.connectionError}
        isGenerating={state.isGenerating}
        focusedPane={focus}
        cwd={state.status.cwd}
        model={state.status.model}
        contextPercent={state.status.contextPercent}
        width={terminalWidth}
        onSubmit={(value) => send({ type: "input", content: value })}
        onInterrupt={() => send({ type: "interrupt" })}
        onCopyLast={() => send({ type: "copy_last_response" })}
      />
      <Box flexGrow={1} />
    </Box>
  );
}
