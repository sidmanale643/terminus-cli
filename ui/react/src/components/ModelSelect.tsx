import React, { useMemo, useState } from "react";
import { Box, Text, useInput } from "ink";
import { COLORS } from "../theme.js";
import type { ModelOption } from "../bridge/protocol.js";
import { formatPrice } from "../helpers/format.js";

interface ModelSelectProps {
  models: ModelOption[];
  currentModel?: string;
  onSelect: (name: string | null) => void;
}

interface ServiceHeaderEntry {
  type: "service_header";
  serviceProvider: string;
}

interface CreatorHeaderEntry {
  type: "creator_header";
  creator: string;
}

interface ModelEntry {
  type: "model";
  index: number;
  model: ModelOption;
}

type Entry = ServiceHeaderEntry | CreatorHeaderEntry | ModelEntry;

export function ModelSelect({ models, currentModel, onSelect }: ModelSelectProps) {
  const { entries, sortedModels } = useMemo(() => {
    const byService = new Map<string, Map<string, ModelOption[]>>();
    for (const m of models) {
      let byCreator = byService.get(m.serviceProvider);
      if (!byCreator) {
        byCreator = new Map();
        byService.set(m.serviceProvider, byCreator);
      }
      const list = byCreator.get(m.creator);
      if (list) list.push(m);
      else byCreator.set(m.creator, [m]);
    }
    const sortedServices = [...byService.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    const result: Entry[] = [];
    const sortedModels: ModelOption[] = [];
    for (const [service, byCreator] of sortedServices) {
      result.push({ type: "service_header", serviceProvider: service });
      const sortedCreators = [...byCreator.entries()].sort((a, b) => a[0].localeCompare(b[0]));
      for (const [creator, list] of sortedCreators) {
        result.push({ type: "creator_header", creator });
        for (const model of list) {
          sortedModels.push(model);
          result.push({ type: "model", index: sortedModels.length - 1, model });
        }
      }
    }
    return { entries: result, sortedModels };
  }, [models]);

  const initialModelIndex = useMemo(() => {
    const i = sortedModels.findIndex((m) => m.name === currentModel);
    return i >= 0 ? i : 0;
  }, [sortedModels, currentModel]);

  const [selectedIndex, setSelectedIndex] = useState(initialModelIndex);

  useInput((input, key) => {
    if (key.upArrow) {
      setSelectedIndex((prev) => (prev === 0 ? sortedModels.length - 1 : prev - 1));
    } else if (key.downArrow) {
      setSelectedIndex((prev) => (prev === sortedModels.length - 1 ? 0 : prev + 1));
    } else if (key.return) {
      onSelect(sortedModels[selectedIndex]?.name ?? null);
    } else if (key.escape || (key.ctrl && input === "c")) {
      onSelect(null);
    }
  });

  let modelCursor = 0;
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        <Text color={COLORS.accent} bold>
          Select model
        </Text>
      </Box>
      {entries.map((entry, i) => {
        if (entry.type === "service_header") {
          return (
            <Box key={`s-${entry.serviceProvider}`}>
              <Text color={COLORS.accent} bold>
                {entry.serviceProvider}
              </Text>
            </Box>
          );
        }
        if (entry.type === "creator_header") {
          return (
            <Box key={`c-${entry.creator}`} paddingLeft={1}>
              <Text color={COLORS.subtle} dimColor>
                {entry.creator}
              </Text>
            </Box>
          );
        }
        const model = entry.model;
        const idx = modelCursor++;
        const selected = idx === selectedIndex;
        const current = model.name === currentModel;
        return (
          <Box key={model.name} paddingLeft={2}>
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
              {model.name}
            </Text>
            {current && (
              <Text color={COLORS.success}>
                {" current"}
              </Text>
            )}
            <Text color={COLORS.muted} dimColor>
              {`  ${model.contextSize.toLocaleString()} ctx  ${formatPrice(model.inputPricing)} in / ${formatPrice(model.outputPricing)} out`}
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
