import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import { COLORS } from "../theme.js";

interface ApiKeyInputProps {
  provider: string;
  onSubmit: (key: string) => void;
  onCancel: () => void;
}

export function ApiKeyInput({ provider, onSubmit, onCancel }: ApiKeyInputProps) {
  const [key, setKey] = useState("");

  useInput((inputChar, keyMeta) => {
    if (keyMeta.return) {
      if (key.trim()) {
        onSubmit(key);
      }
    } else if (keyMeta.escape || (keyMeta.ctrl && inputChar === "c")) {
      onCancel();
    } else if (keyMeta.backspace || keyMeta.delete) {
      setKey((prev) => prev.slice(0, -1));
    } else if (!keyMeta.ctrl && !keyMeta.meta && inputChar.length >= 1) {
      setKey((prev) => prev + inputChar);
    }
  });

  const masked = "*".repeat(key.length);

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        <Text color={COLORS.accent} bold>
          {`Enter API key for ${provider}`}
        </Text>
      </Box>
      <Box>
        <Text color={COLORS.accent} dimColor>
          {"  "}
        </Text>
        <Text color={COLORS.text}>{key.length > 0 ? masked : ""}</Text>
        <Text color={COLORS.accent}>{"█"}</Text>
      </Box>
      <Box>
        <Text color={COLORS.muted} dimColor>
          Enter confirms · Esc cancels
        </Text>
      </Box>
    </Box>
  );
}
