import type { InboundMessage, ModelOption, CommandOption, ProviderOption } from "./protocol.js";

export interface ToolCallInfo {
  toolName: string;
  label: string;
  args: Record<string, unknown>;
}

export interface ChatMessage {
  type: string;
  content: string;
  tag?: string;
  toolCall?: ToolCallInfo;
  expanded?: boolean;
}

export interface BridgeState {
  banner: { logo: string[]; subtitle?: string } | null;
  status: { cwd: string; model: string; contextPercent: number };
  commands: CommandOption[];
  requestingInput: boolean;
  messages: ChatMessage[];
  streamingContent: string;
  modelSelect: { models: ModelOption[]; currentModel?: string } | null;
  providerSelect: { providers: ProviderOption[] } | null;
  apiKeyRequest: { provider: string } | null;
  connected: boolean;
  connectionError: string | null;
}

export const initialState: BridgeState = {
  banner: null,
  status: { cwd: "", model: "", contextPercent: 0 },
  commands: [],
  requestingInput: false,
  messages: [],
  streamingContent: "",
  modelSelect: null,
  providerSelect: null,
  apiKeyRequest: null,
  connected: false,
  connectionError: null,
};

export type BridgeAction =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "connection_error"; error: string }
  | { type: "bridge_message"; message: InboundMessage }
  | { type: "input_sent" }
  | { type: "model_selected_sent" }
  | { type: "provider_selected_sent" }
  | { type: "api_key_submitted_sent" }
  | { type: "toggle_thinking"; index: number };

export function bridgeReducer(state: BridgeState, action: BridgeAction): BridgeState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true, connectionError: null };
    case "disconnected":
      return { ...state, connected: false };
    case "connection_error":
      return { ...state, connectionError: action.error };
    case "input_sent":
      return { ...state, requestingInput: false };
    case "model_selected_sent":
      return { ...state, modelSelect: null };
    case "provider_selected_sent":
      return { ...state, providerSelect: null };
    case "api_key_submitted_sent":
      return { ...state, apiKeyRequest: null };
    case "toggle_thinking": {
      const newMessages = [...state.messages];
      const msg = newMessages[action.index];
      if (msg && msg.type === "thinking") {
        newMessages[action.index] = { ...msg, expanded: !msg.expanded };
      }
      return { ...state, messages: newMessages };
    }
    case "bridge_message":
      return applyMessage(state, action.message);
    default:
      return state;
  }
}

function applyMessage(state: BridgeState, msg: InboundMessage): BridgeState {
  switch (msg.type) {
    case "banner":
      return { ...state, banner: { logo: msg.logo, subtitle: msg.subtitle } };
    case "command_list":
      return { ...state, commands: msg.commands };
    case "status":
      return { ...state, status: { cwd: msg.cwd, model: msg.model, contextPercent: msg.contextPercent } };
    case "input_request":
      return { ...state, requestingInput: true };
    case "model_select":
      return { ...state, modelSelect: { models: msg.models, currentModel: msg.currentModel }, requestingInput: false };
    case "provider_select":
      return { ...state, providerSelect: { providers: msg.providers }, requestingInput: false };
    case "api_key_request":
      return { ...state, apiKeyRequest: { provider: msg.provider }, requestingInput: false };
    case "tool_call":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            type: "tool_call",
            content: msg.label,
            toolCall: { toolName: msg.toolName, label: msg.label, args: msg.args },
          },
        ],
      };
    case "response":
      return { ...state, messages: [...state.messages, { type: msg.tag || "assistant", content: msg.content }] };
    case "stream_chunk":
      return { ...state, streamingContent: state.streamingContent + msg.content };
    case "stream_end":
      return { ...state, messages: [...state.messages, { type: "assistant", content: msg.content }], streamingContent: "" };
    case "thinking":
      if (state.messages[state.messages.length - 1]?.type === "thinking") {
        const messages = [...state.messages];
        const last = messages[messages.length - 1];
        messages[messages.length - 1] = {
          ...last,
          content: `${last.content}${msg.content}`,
        };
        return { ...state, messages };
      }
      return { ...state, messages: [...state.messages, { type: "thinking", content: msg.content, expanded: false }] };
    case "alert":
      return { ...state, messages: [...state.messages, { type: "alert", content: msg.content }] };
    case "error":
      return { ...state, messages: [...state.messages, { type: "error", content: msg.message }] };
    case "clear":
      return { ...state, messages: [], streamingContent: "" };
    case "exit":
      return state;
    default:
      return state;
  }
}
