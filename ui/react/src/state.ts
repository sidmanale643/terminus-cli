import type {
  CommandOption,
  InboundEnvelope,
  InboundMessage,
  ModelOption,
  ProviderOption,
  SkillOption,
} from "./protocol.js";

const MAX_TRANSCRIPT_ITEMS = 300;
const MAX_WORKER_ACTIVITY_ITEMS = 200;

export interface StatusState {
  cwd: string;
  model: string;
  contextPercent: number;
}

export interface TranscriptItem {
  id: string;
  kind:
    | "response"
    | "error"
    | "alert"
    | "thinking"
    | "tool_call"
    | "tool_output"
    | "worker"
    | "mode";
  title?: string;
  body: string;
  tone?: string;
  preview?: string;
  collapsible?: boolean;
}

export interface TranscriptState {
  order: string[];
  byId: Record<string, TranscriptItem>;
  overflowCount: number;
}

export interface WorkerState {
  id: string;
  title: string;
  status: string;
  role: string;
  summary: string;
  description: string;
  createdAt?: number;
  lastUpdatedAt?: number;
  activityOrder: string[];
  activityById: Record<string, WorkerActivityItem>;
  activityCounts: WorkerActivityCounts;
  result?: string;
  resultEnvelope?: Record<string, unknown>;
}

export type WorkerActivityType = "thinking" | "tool_call" | "tool_output" | "notification" | "status";

export interface WorkerActivityCounts {
  thinking: number;
  toolCall: number;
  toolOutput: number;
}

export interface WorkerActivityItem {
  id: string;
  type: WorkerActivityType;
  title: string;
  content: string;
  preview: string;
  timestamp?: number;
  toolName?: string;
  args?: Record<string, unknown>;
  collapsible: boolean;
}

export interface SelectionState<T> {
  title: string;
  subtitle: string;
  options: T[];
}

export interface StreamingItem {
  id: string;
  content: string;
}

export interface AppState {
  connected: boolean;
  connectionError: string | null;
  banner: { logo: string[]; subtitle?: string } | null;
  showIntro: boolean;
  status: StatusState;
  commands: CommandOption[];
  transcript: TranscriptState;
  workers: WorkerState[];
  inputActive: boolean;
  isGenerating: boolean;
  streams: Record<string, string>;
  completedStreams: Record<string, string>;
  modelSelect: SelectionState<ModelOption> | null;
  providerSelect: SelectionState<ProviderOption> | null;
  skillSelect: SelectionState<SkillOption> | null;
  apiKeyPrompt: { provider: string } | null;
}

export const initialState: AppState = {
  connected: false,
  connectionError: null,
  banner: null,
  showIntro: true,
  status: { cwd: "", model: "", contextPercent: 0 },
  commands: [],
  transcript: { order: [], byId: {}, overflowCount: 0 },
  workers: [],
  inputActive: false,
  isGenerating: false,
  streams: {},
  completedStreams: {},
  modelSelect: null,
  providerSelect: null,
  skillSelect: null,
  apiKeyPrompt: null,
};

type Action =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "connection_error"; error: string }
  | { type: "bridge"; message: InboundEnvelope }
  | { type: "input_sent" }
  | { type: "selection_closed"; selection: "model" | "provider" | "skill" | "apiKey" };

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true, connectionError: null };
    case "disconnected":
      return { ...state, connected: false };
    case "connection_error":
      return { ...state, connectionError: action.error };
    case "input_sent":
      return { ...state, inputActive: false, isGenerating: true, showIntro: false };
    case "selection_closed":
      return closeSelection(state, action.selection);
    case "bridge":
      return applyEnvelope(state, action.message);
    default:
      return state;
  }
}

export function selectTranscriptItems(state: AppState, limit = 120): TranscriptItem[] {
  const visibleIds = state.transcript.order.slice(-limit);
  const items = visibleIds
    .map((id) => state.transcript.byId[id])
    .filter((item): item is TranscriptItem => Boolean(item));

  if (state.transcript.overflowCount === 0) {
    return items;
  }

  return [
    createTranscriptItem(
      "transcript-overflow-summary",
      "alert",
      `${state.transcript.overflowCount} older event(s) hidden from active view.`,
      "history",
      "warning",
    ),
    ...items,
  ];
}

export function selectStreamingItems(state: AppState): StreamingItem[] {
  return Object.entries(state.streams).map(([id, content]) => ({ id, content }));
}

export function selectWorkers(state: AppState): WorkerState[] {
  return state.workers;
}

export function selectWorkerActivity(state: AppState, workerId: string): WorkerActivityItem[] {
  const worker = state.workers.find((candidate) => candidate.id === workerId);
  if (!worker) return [];
  return worker.activityOrder
    .map((id) => worker.activityById[id])
    .filter((item): item is WorkerActivityItem => Boolean(item));
}

function closeSelection(
  state: AppState,
  selection: "model" | "provider" | "skill" | "apiKey",
): AppState {
  if (selection === "model") return { ...state, modelSelect: null };
  if (selection === "provider") return { ...state, providerSelect: null };
  if (selection === "skill") return { ...state, skillSelect: null };
  return { ...state, apiKeyPrompt: null };
}

function applyEnvelope(state: AppState, envelope: InboundEnvelope): AppState {
  if (envelope.type !== "event_batch") {
    return applyInbound(state, envelope);
  }

  return envelope.events.reduce(
    (nextState, message) => applyInbound(nextState, message),
    state,
  );
}

function createTranscriptItem(
  id: string,
  kind: TranscriptItem["kind"],
  body: string,
  title?: string,
  tone?: string,
  preview?: string,
  collapsible?: boolean,
): TranscriptItem {
  return { id, kind, body, title, tone, preview, collapsible };
}

function appendTranscript(state: AppState, item: TranscriptItem): AppState {
  if (shouldDropDuplicateTail(state, item)) {
    return state;
  }

  const order = state.transcript.order.includes(item.id)
    ? state.transcript.order
    : [...state.transcript.order, item.id];
  const transcript = trimTranscript({
    ...state.transcript,
    order,
    byId: { ...state.transcript.byId, [item.id]: item },
  });

  return { ...state, transcript };
}

function shouldDropDuplicateTail(state: AppState, item: TranscriptItem): boolean {
  const previousId = state.transcript.order[state.transcript.order.length - 1];
  const previous = previousId ? state.transcript.byId[previousId] : undefined;

  return Boolean(
    previous &&
      previous.id !== item.id &&
      previous.kind === item.kind &&
      previous.title === item.title &&
      previous.tone === item.tone &&
      previous.body === item.body,
  );
}

function trimTranscript(transcript: TranscriptState): TranscriptState {
  if (transcript.order.length <= MAX_TRANSCRIPT_ITEMS) {
    return transcript;
  }

  const removedIds = transcript.order.slice(0, transcript.order.length - MAX_TRANSCRIPT_ITEMS);
  const byId = { ...transcript.byId };
  for (const id of removedIds) {
    delete byId[id];
  }

  return {
    order: transcript.order.slice(-MAX_TRANSCRIPT_ITEMS),
    byId,
    overflowCount: transcript.overflowCount + removedIds.length,
  };
}

function updateWorker(
  workers: WorkerState[],
  workerId: string,
  patch: Partial<WorkerState>,
): WorkerState[] {
  const existing = workers.find((worker) => worker.id === workerId);
  if (!existing) {
    return [
      ...workers,
      {
        id: workerId,
        title: patch.title ?? workerId,
        role: patch.role ?? "worker",
        status: patch.status ?? "running",
        summary: patch.summary ?? "",
        description: patch.description ?? patch.summary ?? "",
        createdAt: patch.createdAt,
        lastUpdatedAt: patch.lastUpdatedAt,
        activityOrder: patch.activityOrder ?? [],
        activityById: patch.activityById ?? {},
        activityCounts: patch.activityCounts ?? {
          thinking: 0,
          toolCall: 0,
          toolOutput: 0,
        },
        result: patch.result,
        resultEnvelope: patch.resultEnvelope,
      },
    ];
  }

  return workers.map((worker) =>
    worker.id === workerId ? { ...worker, ...patch } : worker,
  );
}

function workerTimestamp(message: { timestamp?: number }): number | undefined {
  return typeof message.timestamp === "number" ? message.timestamp : undefined;
}

function compactPreview(value: string, maxLength = 160): string {
  const singleLine = value.replace(/\s+/g, " ").trim();
  if (singleLine.length <= maxLength) return singleLine;
  return `${singleLine.slice(0, Math.max(0, maxLength - 1))}…`;
}

function activityTitle(
  type: WorkerActivityType,
  toolName?: string,
): string {
  if (type === "tool_call") return toolName ? `tool ${toolName}` : "tool call";
  if (type === "tool_output") return toolName ? `${toolName} output` : "tool output";
  if (type === "notification") return "update";
  if (type === "status") return "status";
  return "thinking";
}

function activityCountKey(type: WorkerActivityType): keyof WorkerActivityCounts | null {
  if (type === "thinking") return "thinking";
  if (type === "tool_call") return "toolCall";
  if (type === "tool_output") return "toolOutput";
  return null;
}

function appendWorkerActivity(
  workers: WorkerState[],
  workerId: string,
  activity: WorkerActivityItem,
): WorkerState[] {
  const existing = updateWorker(workers, workerId, {
    lastUpdatedAt: activity.timestamp,
  });

  return existing.map((worker) => {
    if (worker.id !== workerId) return worker;

    const replacingExisting = Boolean(worker.activityById[activity.id]);
    const nextOrder = replacingExisting
      ? worker.activityOrder
      : [...worker.activityOrder, activity.id];
    const overflowIds = nextOrder.slice(0, Math.max(0, nextOrder.length - MAX_WORKER_ACTIVITY_ITEMS));
    const trimmedOrder = nextOrder.slice(-MAX_WORKER_ACTIVITY_ITEMS);
    const activityById = { ...worker.activityById, [activity.id]: activity };
    for (const id of overflowIds) {
      delete activityById[id];
    }

    const countKey = replacingExisting ? null : activityCountKey(activity.type);
    const activityCounts = countKey
      ? {
          ...worker.activityCounts,
          [countKey]: worker.activityCounts[countKey] + 1,
        }
      : worker.activityCounts;

    return {
      ...worker,
      activityOrder: trimmedOrder,
      activityById,
      activityCounts,
      lastUpdatedAt: activity.timestamp ?? worker.lastUpdatedAt,
    };
  });
}

function applyInbound(state: AppState, message: InboundMessage): AppState {
  switch (message.type) {
    case "banner":
      return { ...state, banner: { logo: message.logo, subtitle: message.subtitle } };
    case "command_list":
      return { ...state, commands: message.commands };
    case "status":
      return updateStatus(state, message);
    case "input_request":
      return activateInput(state);
    case "generation_start":
      return { ...state, inputActive: false, isGenerating: true };
    case "generation_end":
      return { ...state, isGenerating: false };
    case "response":
      return appendResponse(state, message);
    case "error":
      return appendError(state, message);
    case "alert":
      return appendAlert(state, message);
    case "thinking":
      return appendThinking(state, message);
    case "tool_call":
      return appendToolCall(state, message);
    case "tool_output":
      return appendToolOutput(state, message);
    case "stream_chunk":
      return appendStreamChunk(state, message.itemId, message.content);
    case "stream_end":
      return finishStream(state, message.itemId, message.content);
    case "worker_spawned":
      return spawnWorker(state, message);
    case "worker_notification":
      return updateWorkerNotification(state, message);
    case "worker_status":
      return updateWorkerStatus(state, message);
    case "worker_detail":
      return appendWorkerDetail(state, message);
    case "model_select":
      return openModelSelect(state, message.models);
    case "provider_select":
      return openProviderSelect(state, message.providers);
    case "skill_select":
      return openSkillSelect(state, message.skills);
    case "api_key_request":
      return { ...state, inputActive: false, apiKeyPrompt: { provider: message.provider } };
    case "mode_switch":
      return appendModeSwitch(state, message.mode, message.note);
    case "clear":
      return clearTimeline(state);
    case "exit":
      return state;
    default:
      return state;
  }
}

function updateStatus(
  state: AppState,
  message: Extract<InboundMessage, { type: "status" }>,
): AppState {
  return {
    ...state,
    status: {
      cwd: message.cwd,
      model: message.model,
      contextPercent: Number.isFinite(message.contextPercent) ? message.contextPercent : 0,
    },
  };
}

function activateInput(state: AppState): AppState {
  return {
    ...state,
    inputActive: true,
    isGenerating: false,
    modelSelect: null,
    providerSelect: null,
    skillSelect: null,
    apiKeyPrompt: null,
  };
}

function appendResponse(
  state: AppState,
  message: Extract<InboundMessage, { type: "response" }>,
): AppState {
  if (state.completedStreams[message.id ?? ""] === message.content) {
    return { ...state, isGenerating: false };
  }

  return appendTranscript(
    { ...state, isGenerating: false },
    createTranscriptItem(
      message.id ?? `response-${state.transcript.order.length + 1}`,
      "response",
      message.content,
      message.tag ?? "assistant",
      message.tag ?? "assistant",
    ),
  );
}

function appendError(
  state: AppState,
  message: Extract<InboundMessage, { type: "error" }>,
): AppState {
  return appendTranscript(
    { ...state, isGenerating: false },
    createTranscriptItem(
      message.id ?? `error-${state.transcript.order.length + 1}`,
      "error",
      message.message,
      "error",
      "error",
    ),
  );
}

function appendAlert(
  state: AppState,
  message: Extract<InboundMessage, { type: "alert" }>,
): AppState {
  return appendTranscript(
    state,
    createTranscriptItem(
      message.id ?? `alert-${state.transcript.order.length + 1}`,
      "alert",
      message.content,
      message.severity ?? "warning",
      "warning",
    ),
  );
}

function appendThinking(
  state: AppState,
  message: Extract<InboundMessage, { type: "thinking" }>,
): AppState {
  return appendTranscript(
    state,
    createTranscriptItem(
      message.id ?? `thinking-${state.transcript.order.length + 1}`,
      "thinking",
      message.content,
      "thinking",
      "thinking",
      message.preview,
      message.collapsible,
    ),
  );
}

function appendToolCall(
  state: AppState,
  message: Extract<InboundMessage, { type: "tool_call" }>,
): AppState {
  return appendTranscript(
    state,
    createTranscriptItem(
      message.id ?? `tool-call-${state.transcript.order.length + 1}`,
      "tool_call",
      JSON.stringify(message.args, null, 2),
      message.label || message.toolName,
      "tool",
      undefined,
      message.collapsible,
    ),
  );
}

function appendToolOutput(
  state: AppState,
  message: Extract<InboundMessage, { type: "tool_output" }>,
): AppState {
  return appendTranscript(
    state,
    createTranscriptItem(
      message.id ?? `tool-output-${state.transcript.order.length + 1}`,
      "tool_output",
      message.content,
      `${message.toolName} output`,
      "muted",
      message.preview,
      message.collapsible,
    ),
  );
}

function appendStreamChunk(state: AppState, itemId: string, content: string): AppState {
  return {
    ...state,
    streams: {
      ...state.streams,
      [itemId]: `${state.streams[itemId] ?? ""}${content}`,
    },
  };
}

function finishStream(state: AppState, itemId: string, content: string): AppState {
  const { [itemId]: _finishedStream, ...streams } = state.streams;
  const completedStreams = { ...state.completedStreams, [itemId]: content };

  return appendTranscript(
    { ...state, streams, completedStreams, isGenerating: false },
    createTranscriptItem(itemId, "response", content, "assistant", "assistant"),
  );
}

function spawnWorker(
  state: AppState,
  message: Extract<InboundMessage, { type: "worker_spawned" }>,
): AppState {
  const workers = updateWorker(state.workers, message.workerId, {
    title: message.name,
    role: message.role ?? "worker",
    status: "running",
    summary: message.description,
    description: message.description,
    createdAt: workerTimestamp(message),
    lastUpdatedAt: workerTimestamp(message),
  });

  return appendTranscript(
    { ...state, workers },
    createTranscriptItem(
      `worker-spawned-${message.workerId}`,
      "worker",
      message.description,
      `${message.name} [${message.role ?? "worker"}]`,
      "worker",
    ),
  );
}

function updateWorkerNotification(
  state: AppState,
  message: Extract<InboundMessage, { type: "worker_notification" }>,
): AppState {
  const workers = updateWorker(state.workers, message.workerId, {
    status: message.status,
    summary: message.summary,
    lastUpdatedAt: workerTimestamp(message),
  });

  return appendTranscript(
    {
      ...state,
      workers: appendWorkerActivity(workers, message.workerId, {
        id: message.id ?? `worker-note-${message.workerId}-${state.transcript.order.length + 1}`,
        type: "notification",
        title: `${message.workerId} ${message.status}`,
        content: message.finalResponse ?? message.summary,
        preview: compactPreview(message.finalResponse ?? message.summary),
        timestamp: workerTimestamp(message),
        collapsible: true,
      }),
    },
    createTranscriptItem(
      message.id ?? `worker-note-${message.workerId}`,
      "worker",
      message.finalResponse ?? message.summary,
      `${message.workerId} ${message.status}`,
      "worker",
    ),
  );
}

function updateWorkerStatus(
  state: AppState,
  message: Extract<InboundMessage, { type: "worker_status" }>,
): AppState {
  const resultText =
    message.result ??
    (message.resultEnvelope ? JSON.stringify(message.resultEnvelope, null, 2) : "");
  const workers = updateWorker(state.workers, message.workerId, {
    status: message.status,
    summary: resultText || message.status,
    result: resultText,
    resultEnvelope: message.resultEnvelope,
    lastUpdatedAt: workerTimestamp(message),
  });

  return appendTranscript(
    {
      ...state,
      workers: appendWorkerActivity(workers, message.workerId, {
        id: message.id ?? `worker-status-${message.workerId}-${state.transcript.order.length + 1}`,
        type: "status",
        title: `${message.workerId} ${message.status}`,
        content: resultText || message.status,
        preview: compactPreview(resultText || message.status),
        timestamp: workerTimestamp(message),
        collapsible: true,
      }),
    },
    createTranscriptItem(
      message.id ?? `worker-status-${message.workerId}`,
      "worker",
      resultText || message.status,
      `${message.workerId} ${message.status}`,
      "worker",
      undefined,
      true,
    ),
  );
}

function appendWorkerDetail(
  state: AppState,
  message: Extract<InboundMessage, { type: "worker_detail" }>,
): AppState {
  const type = isWorkerActivityType(message.detailType)
    ? message.detailType
    : "notification";
  const id = message.id ?? `worker-detail-${message.workerId}-${message.detailType}-${state.transcript.order.length + 1}`;

  return {
    ...state,
    workers: appendWorkerActivity(state.workers, message.workerId, {
      id,
      type,
      title: activityTitle(type, message.toolName),
      content: message.content,
      preview: compactPreview(message.content),
      timestamp: workerTimestamp(message),
      toolName: message.toolName,
      args: message.args,
      collapsible: true,
    }),
  };
}

function isWorkerActivityType(value: string): value is WorkerActivityType {
  return value === "thinking" || value === "tool_call" || value === "tool_output";
}

function openModelSelect(state: AppState, models: ModelOption[]): AppState {
  return {
    ...state,
    inputActive: false,
    modelSelect: {
      title: "Select model",
      subtitle: "Choose the active model for this session.",
      options: models,
    },
  };
}

function openProviderSelect(state: AppState, providers: ProviderOption[]): AppState {
  return {
    ...state,
    inputActive: false,
    providerSelect: {
      title: "Connect provider",
      subtitle: "Choose which API provider to configure.",
      options: providers,
    },
  };
}

function openSkillSelect(state: AppState, skills: SkillOption[]): AppState {
  return {
    ...state,
    inputActive: false,
    skillSelect: {
      title: "Load skill",
      subtitle: "Choose a project skill to inject into context.",
      options: skills,
    },
  };
}

function appendModeSwitch(state: AppState, mode: string, note?: string): AppState {
  return appendTranscript(
    state,
    createTranscriptItem(
      `mode-${state.transcript.order.length + 1}`,
      "mode",
      note ? `Switched to ${mode} mode.\n${note}` : `Switched to ${mode} mode.`,
      "mode",
      "muted",
    ),
  );
}

function clearTimeline(state: AppState): AppState {
  return {
    ...state,
    transcript: { order: [], byId: {}, overflowCount: 0 },
    streams: {},
    completedStreams: {},
    workers: [],
    isGenerating: false,
  };
}
