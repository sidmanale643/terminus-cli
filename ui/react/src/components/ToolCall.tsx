import React from "react";
import { Box, Text } from "ink";
import { COLORS } from "../theme.js";
import type { ToolCallInfo } from "../bridge/state.js";

const TOOL_SHORT_NAMES: Record<string, string> = {
  grep_search: "grep",
  file_reader: "read",
  file_editor: "edit",
  file_creator: "create",
  multi_edit: "multi-edit",
  multiple_file_reader: "read",
  command_executor: "run",
  ls: "ls",
  web_search: "search",
  todo: "todo",
  subagent: "delegate",
  lint: "lint",
  ask_question: "ask",
};

function extractParam(args: Record<string, unknown>): string | null {
  if (args.file_path) {
    const path = String(args.file_path);
    const parts = path.split("/");
    return parts[parts.length - 1] || path;
  }
  if (args.pattern) {
    const p = String(args.pattern);
    return p.length > 35 ? p.slice(0, 35) + "\u2026" : p;
  }
  if (args.command) {
    const c = String(args.command);
    return c.length > 35 ? c.slice(0, 35) + "\u2026" : c;
  }
  if (args.query) {
    const q = String(args.query);
    return q.length > 35 ? q.slice(0, 35) + "\u2026" : q;
  }
  if (args.task) {
    const t = String(args.task);
    return t.length > 35 ? t.slice(0, 35) + "\u2026" : t;
  }
  if (args.directory) {
    const d = String(args.directory);
    const parts = d.split("/");
    return parts[parts.length - 1] || d;
  }
  if (args.file_paths && Array.isArray(args.file_paths)) {
    return `${args.file_paths.length} files`;
  }
  return null;
}

interface ToolCallProps {
  toolCall: ToolCallInfo;
}

export function ToolCall({ toolCall }: ToolCallProps) {
  const shortName = TOOL_SHORT_NAMES[toolCall.toolName] || toolCall.toolName;
  const param = extractParam(toolCall.args);
  const argsKeys = Object.keys(toolCall.args);
  const summary =
    param ||
    (argsKeys.length > 0
      ? argsKeys.map((k) => {
          const v = toolCall.args[k];
          const s = Array.isArray(v) ? `[${v.length} items]` : String(v).slice(0, 40);
          return `${k}: ${s}`;
        }).join(", ")
      : toolCall.label);

  return (
    <Box flexDirection="row">
      <Text color={COLORS.accent}>{shortName}</Text>
      {summary ? (
        <>
          <Text color={COLORS.subtle}> {"\u2192"} </Text>
          <Text color={COLORS.muted} dimColor>
            {summary}
          </Text>
        </>
      ) : (
        <Text color={COLORS.subtle}> </Text>
      )}
    </Box>
  );
}
