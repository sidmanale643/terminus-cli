import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import { COLORS } from "../theme.js";
import type { ProviderOption } from "../bridge/protocol.js";

interface ProviderSelectProps {
  providers: ProviderOption[];
  onSelect: (name: string | null) => void;
}

export function ProviderSelect({ providers, onSelect }: ProviderSelectProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  useInput((input, key) => {
    if (key.upArrow) {
      setSelectedIndex((prev) => (prev === 0 ? providers.length - 1 : prev - 1));
    } else if (key.downArrow) {
      setSelectedIndex((prev) => (prev === providers.length - 1 ? 0 : prev + 1));
    } else if (key.return) {
      onSelect(providers[selectedIndex]?.name ?? null);
    } else if (key.escape || (key.ctrl && input === "c")) {
      onSelect(null);
    }
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        <Text color={COLORS.accent} bold>
          Select provider
        </Text>
      </Box>
      {providers.map((provider, index) => {
        const selected = index === selectedIndex;
        return (
          <Box key={provider.name}>
            <Text
              color={selected ? COLORS.selectionText : COLORS.muted}
              backgroundColor={selected ? COLORS.selection : undefined}
            >
              {selected ? "› " : "  "}
            </Text>
            <Text
              color={selected ? COLORS.selectionText : COLORS.text}
              backgroundColor={selected ? COLORS.selection : undefined}
              bold={selected}
            >
              {provider.name}
            </Text>
            <Text color={COLORS.muted} dimColor>
              {"  "}{provider.description}
            </Text>
          </Box>
        );
      })}
      <Box>
        <Text color={COLORS.muted} dimColor>
          Enter selects · Esc cancels
        </Text>
      </Box>
    </Box>
  );
}
