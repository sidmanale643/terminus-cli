export interface CommandOption {
  name: string;
  description: string;
}

export interface ModelOption {
  name: string;
  provider: string;
  creator: string;
  serviceProvider: string;
  contextSize: number;
  inputPricing: number;
  outputPricing: number;
}

export interface ProviderOption {
  name: string;
  description: string;
}

export interface SkillOption {
  name: string;
  description: string;
  trigger?: string;
}

export interface BackendEventMetadata {
  seq?: number;
  turnId?: string;
  timestamp?: number;
}

export type InboundMessage = BackendEventMetadata & (
  | { type: "banner"; logo: string[]; subtitle?: string }
  | { type: "command_list"; commands: CommandOption[] }
  | { type: "status"; cwd: string; model: string; contextPercent: number }
  | { type: "input_request" }
  | { type: "generation_start" }
  | { type: "generation_end" }
  | { type: "response"; id?: string; content: string; tag?: string }
  | { type: "error"; id?: string; message: string; severity?: string }
  | { type: "alert"; id?: string; content: string; severity?: string }
  | { type: "thinking"; id?: string; content: string; preview?: string; collapsible?: boolean }
  | { type: "tool_call"; id?: string; toolName: string; label: string; args: Record<string, unknown>; collapsible?: boolean }
  | { type: "tool_output"; id?: string; toolName: string; content: string; preview?: string; collapsible?: boolean }
  | { type: "stream_chunk"; itemId: string; content: string }
  | { type: "stream_end"; itemId: string; content: string }
  | { type: "worker_spawned"; workerId: string; name: string; description: string; role?: string }
  | { type: "worker_notification"; id?: string; workerId: string; status: string; summary: string; finalResponse?: string; timestamp?: number }
  | { type: "worker_status"; id?: string; workerId: string; status: string; result?: string; resultEnvelope?: Record<string, unknown>; timestamp?: number }
  | { type: "worker_detail"; id?: string; workerId: string; detailType: string; content: string; toolName?: string; args?: Record<string, unknown>; timestamp?: number }
  | { type: "model_select"; models: ModelOption[]; currentModel?: string }
  | { type: "provider_select"; providers: ProviderOption[] }
  | { type: "api_key_request"; provider: string }
  | { type: "skill_select"; skills: SkillOption[] }
  | { type: "mode_switch"; mode: string; note?: string }
  | { type: "clear" }
  | { type: "exit" }
);

export interface EventBatch {
  type: "event_batch";
  events: InboundMessage[];
}

export type InboundEnvelope = InboundMessage | EventBatch;

export type OutboundMessage =
  | { type: "ready" }
  | { type: "input"; content: string }
  | { type: "interrupt" }
  | { type: "copy_last_response" }
  | { type: "model_selected"; name: string | null }
  | { type: "provider_selected"; name: string | null }
  | { type: "api_key_submitted"; key: string }
  | { type: "skill_selected"; name: string | null };

export function parseJsonLines(buffer: string): {
  messages: InboundEnvelope[];
  remainder: string;
} {
  const messages: InboundEnvelope[] = [];
  let remainder = buffer;

  while (remainder.includes("\n")) {
    const splitIndex = remainder.indexOf("\n");
    const line = remainder.slice(0, splitIndex).trim();
    remainder = remainder.slice(splitIndex + 1);
    if (!line) {
      continue;
    }
    try {
      messages.push(JSON.parse(line) as InboundEnvelope);
    } catch {
      // Ignore malformed non-protocol lines from child stderr noise.
    }
  }

  return { messages, remainder };
}

export function encodeMessage(message: OutboundMessage): string {
  return `${JSON.stringify(message)}\n`;
}
