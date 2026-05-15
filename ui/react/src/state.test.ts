import assert from "node:assert/strict";
import {
  initialState,
  reducer,
  selectStreamingItems,
  selectTranscriptItems,
  selectWorkerActivity,
  selectWorkers,
} from "./state.js";

const seededState = reducer(initialState, {
  type: "bridge",
  message: { type: "banner", logo: ["TERMINUS"], subtitle: "Your coding sidekick" },
});

const afterSubmit = reducer(seededState, { type: "input_sent" });
assert.equal(afterSubmit.inputActive, false);
assert.equal(afterSubmit.isGenerating, true);
assert.equal(afterSubmit.showIntro, false);
assert.deepEqual(afterSubmit.banner, seededState.banner);

const afterBatch = reducer(afterSubmit, {
  type: "bridge",
  message: {
    type: "event_batch",
    events: [
      { type: "generation_start", seq: 1 },
      { type: "thinking", id: "think-1", content: "first", collapsible: true, seq: 2 },
      { type: "thinking", id: "think-1", content: "updated", collapsible: true, seq: 3 },
      { type: "tool_output", id: "tool-1", toolName: "read_file", content: "done", seq: 4 },
    ],
  },
});
assert.equal(afterBatch.isGenerating, true);
assert.deepEqual(
  selectTranscriptItems(afterBatch).map((item) => item.body),
  ["updated", "done"],
);

const afterStreamChunk = reducer(afterBatch, {
  type: "bridge",
  message: { type: "stream_chunk", itemId: "response-1", content: "hel" },
});
const afterSecondStreamChunk = reducer(afterStreamChunk, {
  type: "bridge",
  message: { type: "stream_chunk", itemId: "response-1", content: "lo" },
});
assert.deepEqual(selectStreamingItems(afterSecondStreamChunk), [
  { id: "response-1", content: "hello" },
]);

const afterStreamEnd = reducer(afterSecondStreamChunk, {
  type: "bridge",
  message: { type: "stream_end", itemId: "response-1", content: "hello" },
});
assert.equal(afterStreamEnd.isGenerating, false);
assert.deepEqual(selectStreamingItems(afterStreamEnd), []);

const afterDuplicateResponse = reducer(afterStreamEnd, {
  type: "bridge",
  message: { type: "response", id: "response-1", content: "hello" },
});
assert.deepEqual(
  selectTranscriptItems(afterDuplicateResponse).map((item) => item.id),
  selectTranscriptItems(afterStreamEnd).map((item) => item.id),
);

const afterWorkerSpawn = reducer(afterDuplicateResponse, {
  type: "bridge",
  message: {
    type: "worker_spawned",
    workerId: "worker-1",
    name: "Explorer",
    description: "checking",
  },
});
const afterWorkerStatus = reducer(afterWorkerSpawn, {
  type: "bridge",
  message: {
    type: "worker_status",
    id: "worker-status-worker-1",
    workerId: "worker-1",
    status: "running",
    result: "half",
  },
});
const afterWorkerStatusUpdate = reducer(afterWorkerStatus, {
  type: "bridge",
  message: {
    type: "worker_status",
    id: "worker-status-worker-1",
    workerId: "worker-1",
    status: "completed",
    result: "done",
  },
});
assert.equal(afterWorkerStatusUpdate.workers[0]?.status, "completed");
assert.equal(
  selectTranscriptItems(afterWorkerStatusUpdate).find((item) => item.id === "worker-status-worker-1")?.body,
  "done",
);
assert.deepEqual(
  selectWorkers(afterWorkerStatusUpdate).map((worker) => ({
    id: worker.id,
    title: worker.title,
    status: worker.status,
  })),
  [{ id: "worker-1", title: "Explorer", status: "completed" }],
);

const afterWorkerThinking = reducer(afterWorkerStatusUpdate, {
  type: "bridge",
  message: {
    type: "worker_detail",
    id: "worker-detail-worker-1-thinking-1",
    workerId: "worker-1",
    detailType: "thinking",
    content: "first thought",
  },
});
const afterWorkerToolCall = reducer(afterWorkerThinking, {
  type: "bridge",
  message: {
    type: "worker_detail",
    id: "worker-detail-worker-1-tool-call-1",
    workerId: "worker-1",
    detailType: "tool_call",
    content: "reading files",
    toolName: "read_file",
    args: { path: "src/main.py" },
  },
});
const afterWorkerToolOutput = reducer(afterWorkerToolCall, {
  type: "bridge",
  message: {
    type: "worker_detail",
    id: "worker-detail-worker-1-tool-output-1",
    workerId: "worker-1",
    detailType: "tool_output",
    content: "file contents",
    toolName: "read_file",
  },
});

assert.deepEqual(
  selectWorkerActivity(afterWorkerToolOutput, "worker-1").map((activity) => activity.content),
  ["done", "first thought", "reading files", "file contents"],
);
assert.deepEqual(afterWorkerToolOutput.workers[0]?.activityCounts, {
  thinking: 1,
  toolCall: 1,
  toolOutput: 1,
});
assert.equal(
  selectTranscriptItems(afterWorkerToolOutput).some((item) => item.id === "worker-detail-worker-1-thinking-1"),
  false,
);

let afterManyWorkerDetails = afterWorkerToolOutput;
for (let index = 0; index < 205; index += 1) {
  afterManyWorkerDetails = reducer(afterManyWorkerDetails, {
    type: "bridge",
    message: {
      type: "worker_detail",
      id: `worker-detail-worker-1-thinking-bulk-${index}`,
      workerId: "worker-1",
      detailType: "thinking",
      content: `bulk ${index}`,
    },
  });
}
const trimmedActivity = selectWorkerActivity(afterManyWorkerDetails, "worker-1");
assert.equal(trimmedActivity.length, 200);
assert.equal(trimmedActivity[0]?.content, "bulk 5");
assert.equal(trimmedActivity.at(-1)?.content, "bulk 204");

const afterClear = reducer(afterManyWorkerDetails, {
  type: "bridge",
  message: { type: "clear" },
});
assert.deepEqual(selectTranscriptItems(afterClear), []);
assert.deepEqual(selectStreamingItems(afterClear), []);
assert.deepEqual(afterClear.workers, []);
