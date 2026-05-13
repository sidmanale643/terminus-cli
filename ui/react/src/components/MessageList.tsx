import React from "react";
import { Box, Text } from "ink";
import { Markdown } from "./Markdown.js";
import { COLORS } from "../theme.js";
import type { ChatMessage } from "../hooks/useBridge.js";
import { getMessageColor } from "../helpers/format.js";
import { ToolCall } from "./ToolCall.js";

interface MessageListProps {
  messages: ChatMessage[];
  streamingContent: string;
}

export function MessageList({ messages, streamingContent }: MessageListProps) {
  return (
    <Box flexDirection="column" paddingX={1}>
      {messages.map((msg, idx) => {
        const key = `${msg.type}-${idx}`;
        if (msg.type === "tool_call" && msg.toolCall) {
          return <ToolCall key={key} toolCall={msg.toolCall} />;
        }
        if (msg.type === "thinking") {
          return (
            <Box key={key} flexDirection="column" marginBottom={1}>
              <Box>
                <Text color={COLORS.warning} bold>💭 Thinking</Text>
              </Box>
              {msg.content && (
                <Box paddingLeft={2}>
                  <Text color={COLORS.muted} dimColor>{msg.content}</Text>
                </Box>
              )}
            </Box>
          );
        }
        if (msg.type === "alert") {
          return (
            <Box key={key} flexDirection="column" marginBottom={1} paddingX={1} paddingY={1} borderStyle="round" borderColor={COLORS.warning}>
              <Box>
                <Text color={COLORS.warning} bold>⚠ Alert</Text>
              </Box>
              <Box paddingLeft={1}>
                <Text color={COLORS.text}>{msg.content}</Text>
              </Box>
            </Box>
          );
        }
        const { color } = getMessageColor(msg.type);
        return (
          <Box key={key} flexDirection="column" marginBottom={1}>
            <Markdown color={color}>{msg.content}</Markdown>
          </Box>
        );
      })}
      {streamingContent && (
        <Box flexDirection="column" marginBottom={1}>
          <Text color={COLORS.text} wrap="wrap">{streamingContent}</Text>
          <Text color={COLORS.accent}>{"▌"}</Text>
        </Box>
      )}
    </Box>
  );
}