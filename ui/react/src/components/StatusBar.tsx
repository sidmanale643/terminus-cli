import React from "react";
import { Box, Text } from "ink";
import { COLORS, createProgressBar, getContextColor } from "../theme.js";

interface StatusBarProps {
  cwd: string;
  model: string;
  contextPercent: number;
}

export function StatusBar({ cwd, model, contextPercent }: StatusBarProps) {
  const bar = createProgressBar(contextPercent, 20);
  const color = getContextColor(contextPercent);

  return (
    <Box
      flexDirection="row"
      justifyContent="space-between"
      paddingX={1}
      marginTop={1}
    >
      <Box>
        <Text color={COLORS.muted} dimColor>
          {"cwd "}
        </Text>
        <Text color={COLORS.text}>{cwd || "."}</Text>
      </Box>
      <Box>
        <Text color={COLORS.muted} dimColor>
          {"model "}
        </Text>
        <Text color={COLORS.accent} bold>
          {model || "—"}
        </Text>
        <Text color={COLORS.muted} dimColor>
          {"   context "}
        </Text>
        <Text color={COLORS.muted} dimColor>
          {"["}
        </Text>
        <Text color={color}>{bar}</Text>
        <Text color={COLORS.muted} dimColor>
          {"] "}
        </Text>
        <Text color={color}>{`${contextPercent.toFixed(1)}%`}</Text>
      </Box>
    </Box>
  );
}
