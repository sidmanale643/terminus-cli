import React, { useState, useEffect, useRef } from "react";
import { Box, Text } from "ink";
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

const LOGO_LINES = [
  "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗██╗   ██╗███████╗",
  "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██║   ██║██╔════╝",
  "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║██║   ██║███████╗",
  "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██║   ██║╚════██║",
  "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║╚██████╔╝███████║",
  "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝",
];

export function Logo() {
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
    <Box flexDirection="column" alignItems="center">
      {LOGO_LINES.map((line, i) => (
        <Text key={i} color={color} bold>
          {line}
        </Text>
      ))}
      <Text color={COLORS.muted} dimColor>
        Your coding sidekick
      </Text>
    </Box>
  );
}
