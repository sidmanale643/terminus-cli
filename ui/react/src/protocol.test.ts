import assert from "node:assert/strict";
import { parseJsonLines } from "./protocol.js";

const partial = parseJsonLines('{"type":"status","cwd":"/tmp"');
assert.deepEqual(partial.messages, []);
assert.equal(partial.remainder, '{"type":"status","cwd":"/tmp"');

const mixed = parseJsonLines(
  [
    '{"type":"response","id":"r1","content":"ok"}',
    'not-json',
    '{"type":"event_batch","events":[{"type":"generation_start","seq":1},{"type":"generation_end","seq":2}]}',
    '{"type":"status","cwd":"/tmp","model":"m","contextPercent":1}',
    "",
  ].join("\n"),
);

assert.equal(mixed.remainder, "");
assert.equal(mixed.messages.length, 3);
assert.equal(mixed.messages[0]?.type, "response");
assert.equal(mixed.messages[1]?.type, "event_batch");
assert.equal(mixed.messages[2]?.type, "status");

if (mixed.messages[1]?.type !== "event_batch") {
  throw new Error("expected event batch");
}

assert.deepEqual(
  mixed.messages[1].events.map((event) => event.type),
  ["generation_start", "generation_end"],
);
