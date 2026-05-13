import React from "react";
import { Box, Text } from "ink";
import { COLORS } from "../theme.js";

interface BannerProps {
  logo: string[];
  subtitle?: string;
}

export function Banner({ logo, subtitle }: BannerProps) {
  return (
    <Box flexDirection="column" alignItems="center">
      {logo.map((line, i) => (
        <Text key={i} color={COLORS.accent} bold>
          {line}
        </Text>
      ))}
      {subtitle && (
        <Text color={COLORS.muted} dimColor>
          {subtitle}
        </Text>
      )}
    </Box>
  );
}