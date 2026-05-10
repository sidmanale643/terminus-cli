export interface ModelOption {
  name: string;
  provider: string;
  creator: string;
  serviceProvider: string;
  contextSize: number;
  inputPricing: number;
  outputPricing: number;
}

export interface CommandOption {
  name: string;
  description: string;
}

export interface ProviderOption {
  name: string;
  description: string;
}

export type InboundMessage =
  | { type: "banner"; logo: string[]; subtitle?: string }
  | { type: "command_list"; commands: CommandOption[] }
  | { type: "status"; cwd: string; model: string; contextPercent: number }
  | { type: "input_request" }
  | { type: "model_select"; models: ModelOption[]; currentModel?: string }
  | { type: "provider_select"; providers: ProviderOption[] }
  | { type: "api_key_request"; provider: string }
  | { type: "tool_call"; toolName: string; label: string; args: Record<string, unknown> }
  | { type: "response"; content: string; tag?: string }
  | { type: "stream_chunk"; content: string }
  | { type: "stream_end"; content: string }
  | { type: "thinking"; content: string }
  | { type: "error"; message: string }
  | { type: "clear" }
  | { type: "exit" };

export type OutboundMessage =
  | { type: "input"; content: string }
  | { type: "ready" }
  | { type: "interrupt" }
  | { type: "copy_last_response" }
  | { type: "model_selected"; name: string | null }
  | { type: "provider_selected"; name: string }
  | { type: "api_key_submitted"; key: string };

export function parseJsonLines(buffer: string): { messages: InboundMessage[]; remainder: string } {
  const messages: InboundMessage[] = [];
  let remaining = buffer;
  while (remaining.includes("\n")) {
    const idx = remaining.indexOf("\n");
    const line = remaining.slice(0, idx);
    remaining = remaining.slice(idx + 1);
    if (!line.trim()) continue;
    try {
      messages.push(JSON.parse(line) as InboundMessage);
    } catch {
      // ignore non-JSON lines
    }
  }
  return { messages, remainder: remaining };
}

export function encodeOutbound(msg: OutboundMessage): string {
  return JSON.stringify(msg) + "\n";
}
