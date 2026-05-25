import type { WorkerActivityItem, WorkerState } from "./state.js";

const MAX_TOOL_CALL_ROWS = 4;

export interface WorkerPaneActivityLine {
  id: string;
  activity: WorkerActivityItem;
  marker: string;
  label: string;
  detail: string;
}

export type WorkerResultRowKind =
  | "summary"
  | "section"
  | "item"
  | "risk"
  | "next"
  | "fallback"
  | "continuation";

export interface WorkerResultLine {
  kind: WorkerResultRowKind;
  label: string;
  text: string;
}

export type WorkerPaneRow =
  | { type: "result"; id: string; result: WorkerResultLine; status: string }
  | { type: "result_separator"; id: string }
  | { type: "tool_call"; id: string; line: WorkerPaneActivityLine }
  | { type: "activity"; id: string; line: WorkerPaneActivityLine }
  | { type: "waiting"; id: string; text: string }
  | { type: "blank"; id: string };

export function selectWorkerPaneActivity(worker: WorkerState): WorkerActivityItem[] {
  const activity = worker.activityOrder
    .map((id) => worker.activityById[id])
    .filter((item): item is WorkerActivityItem => Boolean(item));

  return activity.filter(isPaneWorthyActivity);
}

export function buildWorkerPaneRows(
  worker: WorkerState,
  width: number,
  bodyRows: number,
): WorkerPaneRow[] {
  const rows = populatedWorkerPaneRows(worker, width, bodyRows);
  return padWorkerPaneRows(worker.id, rows, bodyRows);
}

export function maxWorkerToolCallRows(bodyRows: number): number {
  if (bodyRows <= 1) return 0;
  return Math.min(MAX_TOOL_CALL_ROWS, bodyRows - 1);
}

export function formatWorkerResult(result: string, width: number): string {
  return compactText(readResultSummary(result) || result, width);
}

export function formatWorkerResultRows(
  worker: WorkerState,
  width: number,
  maxRows: number,
): WorkerResultLine[] {
  if (maxRows <= 0) return [];
  const display = readWorkerResultDisplay(worker);
  const lines = display ? resultDisplayLines(display) : [resultLine("fallback", "", worker.result ?? "")];
  return wrapResultLines(lines, width).slice(0, maxRows);
}

export function createWorkerPaneActivityLine(
  activity: WorkerActivityItem,
  width: number,
): WorkerPaneActivityLine {
  const label = compactText(activity.toolName || activity.title || activity.type, 18);
  const detail = formatActivityDetail(activity, Math.max(12, width - label.length - 6));

  return {
    id: activity.id,
    activity,
    marker: workerActivityMarker(activity),
    label,
    detail,
  };
}

export function compactText(value: string, maxLength: number): string {
  const singleLine = value.replace(/\s+/g, " ").trim();
  if (singleLine.length <= maxLength) return singleLine;
  return `${singleLine.slice(0, Math.max(0, maxLength - 1))}…`;
}

function isPaneWorthyActivity(activity: WorkerActivityItem): boolean {
  return activity.type === "tool_call";
}

function formatActivityDetail(activity: WorkerActivityItem, maxLength: number): string {
  if (activity.type === "tool_call") {
    return "";
  }

  if (activity.type === "status") {
    return formatWorkerResult(activity.preview || activity.content, maxLength);
  }

  return compactText(activity.preview || activity.content, maxLength);
}

function readResultSummary(result: string): string {
  try {
    return resultSummaryFromValue(JSON.parse(result));
  } catch {
    return "";
  }
}

function resultSummaryFromValue(value: unknown): string {
  const display = resultDisplayFromValue(value);
  if (display?.whatWasDone) return display.whatWasDone;
  if (display?.fallback) return display.fallback;
  return "";
}

interface WorkerResultDisplay {
  whatWasDone: string;
  evidence: string[];
  unresolvedRisks: string[];
  exactNextStep: string;
  fallback: string;
}

function readWorkerResultDisplay(worker: WorkerState): WorkerResultDisplay | null {
  const envelopeDisplay = resultDisplayFromValue(worker.resultEnvelope);
  if (envelopeDisplay) return envelopeDisplay;
  return resultDisplayFromResultText(worker.result ?? "");
}

function resultDisplayFromResultText(result: string): WorkerResultDisplay | null {
  const parsed = parseJson(result);
  if (parsed !== null) return resultDisplayFromValue(parsed);
  return result.trim() ? emptyResultDisplay({ fallback: result }) : null;
}

function resultDisplayFromValue(value: unknown): WorkerResultDisplay | null {
  if (!isRecord(value)) return null;
  const record = value as Record<string, unknown>;
  const handoff = resultHandoffRecord(record);
  const display = emptyResultDisplay({
    whatWasDone: stringField(handoff, [
      "what_was_done",
      "summary",
      "result",
    ]),
    evidence: stringListField(handoff, ["evidence", "findings", "artifacts"]),
    unresolvedRisks: stringListField(handoff, ["unresolved_risks", "risks"]),
    exactNextStep: stringField(handoff, [
      "exact_next_step",
      "recommended_next_action",
      "next_action",
    ]),
    fallback: stringField(record, ["summary", "result", "message"]),
  });

  return hasResultDisplayContent(display) ? display : null;
}

function resultHandoffRecord(record: Record<string, unknown>): Record<string, unknown> {
  const handoff = record.handoff;
  if (isRecord(handoff)) return { ...record, ...handoff };
  const result = record.result;
  if (isRecord(result) && isRecord(result.handoff)) return { ...record, ...result, ...result.handoff };
  if (isRecord(result)) return { ...record, ...result };
  return record;
}

function resultDisplayLines(display: WorkerResultDisplay): WorkerResultLine[] {
  const lines: WorkerResultLine[] = [];
  appendResultLine(lines, "summary", "done", display.whatWasDone);
  appendResultItems(lines, "evidence", display.evidence, 3);
  appendResultItems(lines, "risk", display.unresolvedRisks, 2);
  appendResultLine(lines, "next", "next", display.exactNextStep);
  appendResultLine(lines, "fallback", "", display.fallback);
  return lines.length ? lines : [resultLine("fallback", "", "")];
}

function appendResultLine(
  lines: WorkerResultLine[],
  kind: WorkerResultRowKind,
  label: string,
  value: string,
): void {
  if (!value.trim()) return;
  lines.push(resultLine(kind, label, value));
}

function appendResultItems(
  lines: WorkerResultLine[],
  label: string,
  values: string[],
  limit: number,
): void {
  const visibleValues = values.slice(0, limit).filter((value) => value.trim());
  if (visibleValues.length === 0) return;
  lines.push(resultLine("section", label, ""));
  visibleValues.forEach((value) => {
    appendResultLine(lines, label === "risk" ? "risk" : "item", "", value);
  });
}

function wrapResultLines(lines: WorkerResultLine[], width: number): WorkerResultLine[] {
  return lines.flatMap((line) => wrapResultText(line, width));
}

function resultLine(
  kind: WorkerResultRowKind,
  label: string,
  text: string,
): WorkerResultLine {
  return { kind, label, text: text.trim() };
}

function emptyResultDisplay(patch: Partial<WorkerResultDisplay>): WorkerResultDisplay {
  return {
    whatWasDone: "",
    evidence: [],
    unresolvedRisks: [],
    exactNextStep: "",
    fallback: "",
    ...patch,
  };
}

function hasResultDisplayContent(display: WorkerResultDisplay): boolean {
  return Boolean(
    display.whatWasDone ||
      display.evidence.length ||
      display.unresolvedRisks.length ||
      display.exactNextStep ||
      display.fallback,
  );
}

function parseJson(value: string): unknown | null {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function stringField(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

function stringListField(record: Record<string, unknown>, keys: string[]): string[] {
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) return value.map(stringFromValue).filter(Boolean);
    if (value !== undefined && value !== null) return [stringFromValue(value)].filter(Boolean);
  }
  return [];
}

function stringFromValue(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (!value || typeof value !== "object") return "";
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function workerActivityMarker(activity: WorkerActivityItem): string {
  if (activity.type === "tool_call") return ">";
  if (activity.type === "notification") return "-";
  if (activity.type === "status") return "•";
  return " ";
}

function populatedWorkerPaneRows(
  worker: WorkerState,
  width: number,
  bodyRows: number,
): WorkerPaneRow[] {
  if (bodyRows <= 0) return [];

  const rows: WorkerPaneRow[] = [];
  const resultRows = createResultRows(worker, width, bodyRows);
  const remainingRows = Math.max(0, bodyRows - resultRows.length);
  const activityBudget = resultRows.length > 0 ? Math.max(0, remainingRows - 1) : remainingRows;
  appendActivityRows(rows, worker, width, activityBudget);
  if (rows.length > 0 && resultRows.length > 0 && rows.length < bodyRows) {
    rows.push({ type: "result_separator", id: `${worker.id}-result-separator` });
  }
  rows.push(...resultRows);
  appendWaitingRow(rows, worker);
  return rows.slice(0, bodyRows);
}

function createResultRows(
  worker: WorkerState,
  width: number,
  bodyRows: number,
): WorkerPaneRow[] {
  if ((!worker.result && !worker.resultEnvelope) || worker.status === "running" || bodyRows <= 0) return [];
  const resultWidth = Math.max(20, width - 3);
  return formatWorkerResultRows(worker, resultWidth, bodyRows)
    .map((result, index) => ({
      type: "result",
      id: `${worker.id}-result-${index}`,
      result,
      status: worker.status,
    }));
}

function appendActivityRows(
  rows: WorkerPaneRow[],
  worker: WorkerState,
  width: number,
  bodyRows: number,
): void {
  const visibleActivity = selectWorkerPaneActivity(worker).slice(-maxWorkerToolCallRows(bodyRows + 1));
  visibleActivity.forEach((activity) => {
    rows.push({
      type: "tool_call",
      id: activity.id,
      line: createWorkerPaneActivityLine(activity, width),
    });
  });
}

function wrapResultText(line: WorkerResultLine, width: number): WorkerResultLine[] {
  const prefix = line.label ? `${line.label}: ` : "";
  const value = `${prefix}${line.text}`;
  const words = value.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  if (words.length === 0) return [line];

  const rows: WorkerResultLine[] = [];
  let current = "";
  words.forEach((word) => {
    if (!current) {
      current = compactText(word, width);
      return;
    }
    if (current.length + word.length + 1 <= width) {
      current = `${current} ${word}`;
      return;
    }
    rows.push(resultLine(rows.length === 0 ? line.kind : "continuation", "", current));
    current = compactText(word, width);
  });
  if (current) {
    rows.push(resultLine(rows.length === 0 ? line.kind : "continuation", "", current));
  }
  return rows;
}

function appendWaitingRow(rows: WorkerPaneRow[], worker: WorkerState): void {
  if (rows.length > 0 || worker.status !== "running") return;
  rows.push({ type: "waiting", id: `${worker.id}-waiting`, text: "waiting" });
}

function padWorkerPaneRows(
  workerId: string,
  rows: WorkerPaneRow[],
  bodyRows: number,
): WorkerPaneRow[] {
  const paddedRows = [...rows];
  while (paddedRows.length < bodyRows) {
    paddedRows.push({ type: "blank", id: `${workerId}-blank-${paddedRows.length}` });
  }
  return paddedRows;
}
