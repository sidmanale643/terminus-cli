import React from "react";
import { Box, Text } from "ink";
import { Markdown } from "./Markdown.js";
import { COLORS } from "../theme.js";
import type { ChatMessage } from "../hooks/useBridge.js";
import { getMessageColor } from "../helpers/format.js";
import { ToolCall } from "./ToolCall.js";

interface ThinkingBlockProps {
  content: string;
  expanded: boolean;
}

function ThinkingBlock({ content, expanded }: ThinkingBlockProps) {
  if (expanded) {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={COLORS.subtle} paddingX={1}>
        <Box>
          <Text color={COLORS.warning} bold>{"💭 Thinking"}</Text>
          <Text color={COLORS.muted} dimColor>{" [Ctrl+T to collapse]"}</Text>
        </Box>
        <Text color={COLORS.muted} dimColor>{content}</Text>
      </Box>
    );
  }
  return (
    <Box>
      <Text color={COLORS.muted} dimColor>{"💭 Thinking... "}</Text>
      <Text color={COLORS.subtle} dimColor>{"[Ctrl+T to expand]"}</Text>
    </Box>
  );
}

interface MessageListProps {
  messages: ChatMessage[];
  streamingContent: string;
}

export function MessageList({ messages, streamingContent }: MessageListProps) {
  return (
    <Box flexDirection="column" paddingX={1}>
      {messages.map((msg, i) => {
        const nextMsg = messages[i + 1];
        const isUserBeforeThinking = msg.type === "user" && nextMsg?.type === "thinking";
        if (msg.type === "tool_call" && msg.toolCall) {
          return <ToolCall key={i} toolCall={msg.toolCall} />;
        }
        if (msg.type === "thinking") {
          return <ThinkingBlock key={i} content={msg.content} expanded={msg.expanded ?? false} />;
        }
        const { color } = getMessageColor(msg.type);
        return (
          <Box key={i} flexDirection="column" marginBottom={isUserBeforeThinking ? 1 : 0}>
            <Markdown color={color}>{msg.content}</Markdown>
          </Box>
        );
      })}
      {streamingContent && (
        <Box flexDirection="column">
          <Markdown color={COLORS.text}>{streamingContent}</Markdown>
          <Text color={COLORS.accent}>{"▌"}</Text>
        </Box>
      )}
    </Box>
  );
}