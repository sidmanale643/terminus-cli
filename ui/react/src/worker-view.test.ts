import assert from "node:assert/strict";
import type { WorkerActivityItem, WorkerState } from "./state.js";
import {
  buildWorkerPaneRows,
  compactText,
  createWorkerPaneActivityLine,
  formatWorkerResult,
  formatWorkerResultRows,
  maxWorkerToolCallRows,
  selectWorkerPaneActivity,
} from "./worker-view.js";

function activity(
  id: string,
  patch: Partial<WorkerActivityItem>,
): WorkerActivityItem {
  return {
    id,
    type: "notification",
    title: "",
    content: "",
    preview: "",
    collapsible: true,
    ...patch,
  };
}

function worker(items: WorkerActivityItem[], patch: Partial<WorkerState> = {}): WorkerState {
  return {
    id: "worker-1",
    title: "Explorer",
    status: "running",
    role: "explorer",
    summary: "",
    description: "",
    activityOrder: items.map((item) => item.id),
    activityById: Object.fromEntries(items.map((item) => [item.id, item])),
    activityCounts: { thinking: 0, toolCall: 0, toolOutput: 0 },
    ...patch,
  };
}

const completedToolCall = activity("call-1", {
  type: "tool_call",
  title: "file_reader",
  toolName: "file_reader",
  args: { file_path: "/Users/sidmanale/Development/terminus-cli/ui/react/src/App.tsx" },
});
const completedToolOutput = activity("output-1", {
  type: "tool_output",
  title: "file_reader",
  toolName: "file_reader",
  content: "File Content: import React from 'react';",
  preview: "File Content: import React from 'react';",
});
const activeToolCall = activity("call-2", {
  type: "tool_call",
  title: "grep_search",
  toolName: "grep_search",
  args: { pattern: "WorkerPane", path: "ui/react/src/App.tsx", include: "*.tsx" },
});

assert.deepEqual(
  selectWorkerPaneActivity(worker([completedToolCall, completedToolOutput, activeToolCall])).map((item) => item.id),
  ["call-1", "call-2"],
);

assert.deepEqual(
  buildWorkerPaneRows(worker([completedToolCall, completedToolOutput, activeToolCall]), 48, 4).map((row) => row.type),
  ["tool_call", "tool_call", "blank", "blank"],
);

const terminalStatus = activity("status-1", {
  type: "status",
  title: "worker-1 completed",
  content: '{"handoff":{"what_was_done":"Worker completed smoke verification."}}',
  preview: '{"handoff":{"what_was_done":"Worker completed smoke verification."}}',
});

assert.deepEqual(
  selectWorkerPaneActivity(worker([completedToolOutput, terminalStatus], {
    status: "completed",
    result: terminalStatus.content,
  })).map((item) => item.id),
  [],
);

assert.deepEqual(
  buildWorkerPaneRows(worker([completedToolOutput, terminalStatus], {
    status: "completed",
    result: terminalStatus.content,
  }), 48, 3).map((row) => row.type),
  ["result", "blank", "blank"],
);

const rollingToolCalls = Array.from({ length: 6 }, (_, index) =>
  activity(`call-${index}`, {
    type: "tool_call",
    title: "grep_search",
    toolName: "grep_search",
    args: { pattern: `WorkerPane${index}` },
  }),
);

assert.equal(maxWorkerToolCallRows(8), 4);
assert.deepEqual(
  buildWorkerPaneRows(worker(rollingToolCalls), 48, 6)
    .filter((row) => row.type === "tool_call")
    .map((row) => row.id),
  ["call-2", "call-3", "call-4", "call-5"],
);

const activeCallLine = createWorkerPaneActivityLine(activeToolCall, 48);
assert.equal(activeCallLine.marker, ">");
assert.equal(activeCallLine.label, "grep_search");
assert.equal(activeCallLine.detail, "");

assert.equal(
  formatWorkerResult('{"handoff":{"what_was_done":"Worker completed smoke verification."}}', 80),
  "Worker completed smoke verification.",
);
assert.deepEqual(
  buildWorkerPaneRows(worker([], {
    status: "completed",
    result: '{"handoff":{"what_was_done":"Worker completed smoke verification and reported a detailed implementation summary."}}',
  }), 36, 3).map((row) => row.type === "result" ? row.result.text : row.type),
  [
    "done: Worker completed smoke",
    "verification and reported a",
    "detailed implementation summary.",
  ],
);

assert.deepEqual(
  formatWorkerResultRows(worker([], {
    status: "completed",
    resultEnvelope: {
      handoff: {
        what_was_done: "Inspected worker board rendering.",
        evidence: ["ui/react/src/App.tsx", "ui/react/src/worker-view.ts"],
        unresolved_risks: ["No browser render pass yet."],
        exact_next_step: "Run React tests.",
      },
    },
  }), 80, 8),
  [
    { kind: "summary", label: "", text: "done: Inspected worker board rendering." },
    { kind: "section", label: "", text: "evidence:" },
    { kind: "item", label: "", text: "ui/react/src/App.tsx" },
    { kind: "item", label: "", text: "ui/react/src/worker-view.ts" },
    { kind: "section", label: "", text: "risk:" },
    { kind: "risk", label: "", text: "No browser render pass yet." },
    { kind: "next", label: "", text: "next: Run React tests." },
  ],
);

assert.deepEqual(
  formatWorkerResultRows(worker([], {
    status: "completed",
    result: JSON.stringify({
      handoff: {
        what_was_done: "Parsed JSON fallback.",
        evidence: ["raw result JSON"],
      },
    }),
  }), 80, 4),
  [
    { kind: "summary", label: "", text: "done: Parsed JSON fallback." },
    { kind: "section", label: "", text: "evidence:" },
    { kind: "item", label: "", text: "raw result JSON" },
  ],
);

assert.deepEqual(
  formatWorkerResultRows(worker([], {
    status: "failed",
    result: "plain worker output",
  }), 80, 4),
  [{ kind: "fallback", label: "", text: "plain worker output" }],
);

assert.deepEqual(
  formatWorkerResultRows(worker([], {
    status: "completed",
    resultEnvelope: {
      handoff: {
        what_was_done: "Worker completed smoke verification and reported a detailed implementation summary.",
      },
    },
  }), 28, 2),
  [
    { kind: "summary", label: "", text: "done: Worker completed smoke" },
    { kind: "continuation", label: "", text: "verification and reported a" },
  ],
);

assert.deepEqual(
  buildWorkerPaneRows(worker([completedToolCall], {
    status: "completed",
    resultEnvelope: {
      handoff: {
        what_was_done: "Inspected worker board rendering.",
      },
    },
  }), 48, 4).map((row) => row.type),
  ["tool_call", "result_separator", "result", "blank"],
);
assert.equal(compactText("  one\n  two\tthree  ", 20), "one two three");
assert.equal(compactText("abcdefghijklmnopqrstuvwxyz", 8), "abcdefg…");
