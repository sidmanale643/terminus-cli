import type { CommandOption } from "../bridge/protocol.js";

export interface InputState {
  text: string;
  cursorPos: number;
  selectedCommandIndex: number;
  commandAccepted: boolean;
  allSelected: boolean;
}

export const initialInputState: InputState = {
  text: "",
  cursorPos: 0,
  selectedCommandIndex: 0,
  commandAccepted: false,
  allSelected: false,
};

export function getCommandQuery(text: string): string {
  return text.startsWith("/") ? text.toLowerCase() : "";
}

export function getVisibleCommands(commandQuery: string, commands: CommandOption[]): CommandOption[] {
  if (!commandQuery) return [];
  return commands
    .filter((cmd) => cmd.name.toLowerCase().startsWith(commandQuery))
    .slice(0, 8);
}

export function getShowCommandMenu(active: boolean, text: string, commandAccepted: boolean): boolean {
  return active && text.startsWith("/") && !commandAccepted;
}

export function clampSelectedIndex(current: number, count: number): number {
  if (count === 0) return 0;
  if (current >= count) return 0;
  return current;
}

export function applyTextInput(state: InputState, char: string): InputState {
  if (state.allSelected) {
    return { ...state, text: char, cursorPos: char.length, allSelected: false, commandAccepted: false };
  }
  const newText = state.text.slice(0, state.cursorPos) + char + state.text.slice(state.cursorPos);
  return { ...state, text: newText, cursorPos: state.cursorPos + 1, commandAccepted: false };
}

export function applyBackspace(state: InputState): InputState {
  if (state.allSelected) {
    return { ...state, text: "", cursorPos: 0, allSelected: false, commandAccepted: false };
  }
  if (state.cursorPos > 0) {
    const newPos = state.cursorPos - 1;
    const newText = state.text.slice(0, newPos) + state.text.slice(state.cursorPos);
    return { ...state, text: newText, cursorPos: newPos, commandAccepted: false };
  }
  return state;
}

export function applyDelete(state: InputState): InputState {
  if (state.cursorPos < state.text.length) {
    const newText = state.text.slice(0, state.cursorPos) + state.text.slice(state.cursorPos + 1);
    return { ...state, text: newText, commandAccepted: false };
  }
  return state;
}

export function applyCursorLeft(state: InputState): InputState {
  return { ...state, cursorPos: Math.max(0, state.cursorPos - 1) };
}

export function applyCursorRight(state: InputState): InputState {
  return { ...state, cursorPos: Math.min(state.text.length, state.cursorPos + 1) };
}

export function selectAll(): InputState {
  return { ...initialInputState, allSelected: true };
}

export function deselectAll(state: InputState, moveToStart: boolean): InputState {
  return {
    ...state,
    allSelected: false,
    cursorPos: moveToStart ? 0 : state.text.length,
  };
}

export type InputAction =
  | { type: "char"; char: string }
  | { type: "backspace" }
  | { type: "delete" }
  | { type: "left" }
  | { type: "right" }
  | { type: "selectAll" }
  | { type: "deselectAll"; moveToStart: boolean };

export function inputReducer(state: InputState, action: InputAction): InputState {
  switch (action.type) {
    case "char":
      return applyTextInput(state, action.char);
    case "backspace":
      return applyBackspace(state);
    case "delete":
      return applyDelete(state);
    case "left":
      return applyCursorLeft(state);
    case "right":
      return applyCursorRight(state);
    case "selectAll":
      return selectAll();
    case "deselectAll":
      return deselectAll(state, action.moveToStart);
    default:
      return state;
  }
}