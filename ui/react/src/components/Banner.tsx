import React, { useState, useEffect, useRef } from "react";
import { Box, Text, Static } from "ink";
import { COLORS } from "../theme.js";

const ACCENT_CYCLE = [
  "#EF4444",
  "#F97316",
  "#EAB308",
  "#22C55E",
  "#3B82F6",
  "#8B5CF6",
  "#EC4899",
  "#EF4444",
];

interface BannerProps {
  logo: string[];
  subtitle?: string;
}

export function Banner({ logo, subtitle }: BannerProps) {
  const [colorIndex, setColorIndex] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setColorIndex((i) => (i + 1) % (ACCENT_CYCLE.length - 1));
    }, 900);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const color = ACCENT_CYCLE[colorIndex];

  return (
    <Static items={[{ logo, subtitle }]}>
      {() => (
        <Box flexDirection="column" alignItems="center">
          {logo.map((line, i) => (
            <Text key={i} color={color} bold>
              {line}
            </Text>
          ))}
          {subtitle && (
            <Text color={COLORS.muted} dimColor>
              {subtitle}
            </Text>
          )}
        </Box>
      )}
    </Static>
  );
}