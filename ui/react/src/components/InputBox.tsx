import React, { useState, useEffect, useRef } from "react";
import { Box, Text, useInput } from "ink";
import { COLORS } from "../theme.js";
import {
  type InputState,
  initialInputState,
  getCommandQuery,
  getVisibleCommands,
  getShowCommandMenu,
  clampSelectedIndex,
  applyTextInput,
  applyBackspace,
  applyCursorLeft,
  applyCursorRight,
  selectAll,
  deselectAll,
} from "../helpers/inputHelpers.js";

interface InputBoxProps {
  active: boolean;
  commands: { name: string; description: string }[];
  onSubmit: (input: string) => void;
  onInterrupt?: () => void;
  onCopyLastResponse?: () => void;
  connectionError?: string | null;
}

const spinnerFrames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

function Spinner() {
  const [frame, setFrame] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setFrame((f) => (f + 1) % spinnerFrames.length);
    }, 80);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  return <Text color={COLORS.accent}>{spinnerFrames[frame]}</Text>;
}

export function InputBox({ active, commands, onSubmit, onInterrupt, onCopyLastResponse, connectionError }: InputBoxProps) {
  const [inputState, setInputState] = useState<InputState>(initialInputState);
  const { text, cursorPos, selectedCommandIndex, commandAccepted, allSelected } = inputState;

  const commandQuery = getCommandQuery(text);
  const visibleCommands = getVisibleCommands(commandQuery, commands);
  const showCommandMenu = getShowCommandMenu(active, text, commandAccepted);

  useInput(
    (inputChar, key) => {
      if (!active) return;

      if (key.ctrl && inputChar === "a") {
        if (text.length > 0) setInputState(selectAll());
        return;
      }

      if (allSelected) {
        if (key.leftArrow || key.rightArrow || key.upArrow || key.downArrow) {
          setInputState(deselectAll(inputState, key.leftArrow));
          return;
        }
      }

      if (key.leftArrow) {
        setInputState(applyCursorLeft(inputState));
        return;
      }
      if (key.rightArrow) {
        setInputState(applyCursorRight(inputState));
        return;
      }

      if (showCommandMenu && key.upArrow && visibleCommands.length > 0) {
        setInputState((prev) => ({
          ...prev,
          selectedCommandIndex: prev.selectedCommandIndex === 0 ? visibleCommands.length - 1 : prev.selectedCommandIndex - 1,
        }));
      } else if (showCommandMenu && key.downArrow && visibleCommands.length > 0) {
        setInputState((prev) => ({
          ...prev,
          selectedCommandIndex: prev.selectedCommandIndex === visibleCommands.length - 1 ? 0 : prev.selectedCommandIndex + 1,
        }));
      } else if (key.return) {
        setInputState((prev) => ({ ...prev, allSelected: false }));
        if (showCommandMenu && visibleCommands[selectedCommandIndex]) {
          const selected = visibleCommands[selectedCommandIndex].name;
          onSubmit(selected);
          setInputState(initialInputState);
          return;
        }
        if (text.trim()) {
          onSubmit(text);
          setInputState(initialInputState);
        }
      } else if (key.backspace || key.delete) {
        setInputState(applyBackspace(inputState));
      } else if (key.ctrl && inputChar === "y") {
        onCopyLastResponse?.();
      } else if (key.ctrl && inputChar === "c") {
        if (onInterrupt) onInterrupt();
      } else if (!key.ctrl && !key.meta && inputChar.length >= 1) {
        setInputState(applyTextInput(inputState, inputChar));
      }
    },
    { isActive: active }
  );

  useEffect(() => {
    if (active) {
      setInputState(initialInputState);
    }
  }, [active]);

  useEffect(() => {
    setInputState((prev) => ({
      ...prev,
      selectedCommandIndex: clampSelectedIndex(selectedCommandIndex, visibleCommands.length),
    }));
  }, [commandQuery]);

  const clampedIndex = clampSelectedIndex(selectedCommandIndex, visibleCommands.length);

  return (
    <Box flexDirection="column" paddingX={1}>
      {connectionError && (
        <Box>
          <Text color={COLORS.danger}>
            {`[ERR] ${connectionError}`}
          </Text>
        </Box>
      )}
      <Box>
        <Text color={COLORS.accent} dimColor>
          {"╭─ "}
        </Text>
        <Text color={COLORS.accent} bold>
          TERMINUS
        </Text>
        {active ? (
          <Text color={COLORS.muted} dimColor>  ready  ctrl+y copy</Text>
        ) : (
          <Box>
            <Text> </Text>
            <Spinner />
          </Box>
        )}
      </Box>
      <Box>
        <Text color={COLORS.accent} dimColor>
          {"╰─› "}
        </Text>
        {allSelected ? (
          <Text color={COLORS.selectionText} backgroundColor={COLORS.selection}>{text}</Text>
        ) : (
          <>
            <Text color={COLORS.text}>{text.slice(0, cursorPos)}</Text>
            <Text color={COLORS.accent}>{"█"}</Text>
            <Text color={COLORS.text}>{text.slice(cursorPos)}</Text>
          </>
        )}
      </Box>
      {showCommandMenu && (
        <Box flexDirection="column" marginLeft={4}>
          {visibleCommands.length > 0 ? (
            visibleCommands.map((command, index) => (
              <Box key={command.name}>
                <Text
                  color={index === clampedIndex ? COLORS.selectionText : COLORS.muted}
                  backgroundColor={index === clampedIndex ? COLORS.selection : undefined}
                >
                  {index === clampedIndex ? "› " : "  "}
                </Text>
                <Text
                  color={index === clampedIndex ? COLORS.selectionText : COLORS.accent}
                  backgroundColor={index === clampedIndex ? COLORS.selection : undefined}
                  bold
                >
                  {command.name.padEnd(14)}
                </Text>
                <Text
                  color={index === clampedIndex ? COLORS.selectionText : COLORS.muted}
                  backgroundColor={index === clampedIndex ? COLORS.selection : undefined}
                >
                  {command.description}
                </Text>
              </Box>
            ))
          ) : (
            <Text color={COLORS.muted} dimColor>
              No matching commands
            </Text>
          )}
        </Box>
      )}
    </Box>
  );
}
