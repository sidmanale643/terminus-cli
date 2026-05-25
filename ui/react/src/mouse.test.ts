import assert from "node:assert/strict";
import {
  findTranscriptMouseHit,
  isSgrMouseInput,
  parseSgrMouseClick,
  parseSgrMouseWheel,
  parseSgrMouseWheels,
  type TranscriptHitArea,
} from "./mouse.js";

const showMoreHitAreas: TranscriptHitArea[] = [
  { id: "thinking-1", row: 2, startColumn: 67, endColumn: 75 },
];

assert.deepEqual(parseSgrMouseClick("\u001B[<0;67;2M"), { x: 67, y: 2 });
assert.deepEqual(parseSgrMouseClick("[<0;67;2M"), { x: 67, y: 2 });
assert.deepEqual(parseSgrMouseClick("\u001B[<16;67;2M"), { x: 67, y: 2 });
assert.deepEqual(parseSgrMouseClick("\u001B[M !!"), { x: 1, y: 1 });

assert.deepEqual(parseSgrMouseWheel("\u001B[<64;67;2M"), { x: 67, y: 2, direction: "up" });
assert.deepEqual(parseSgrMouseWheel("\u001B[<65;67;2M"), { x: 67, y: 2, direction: "down" });
assert.deepEqual(parseSgrMouseWheel("\u001B[<68;67;2M"), { x: 67, y: 2, direction: "up" });
assert.deepEqual(
  parseSgrMouseWheels("\u001B[<64;67;2M\u001B[<65;67;3M"),
  [
    { x: 67, y: 2, direction: "up" },
    { x: 67, y: 3, direction: "down" },
  ],
);

assert.equal(parseSgrMouseClick("\u001B[<0;67;2m"), null);
assert.equal(parseSgrMouseClick("\u001B[<2;67;2M"), null);
assert.equal(parseSgrMouseClick("\u001B[<64;67;2M"), null);
assert.equal(parseSgrMouseClick("not-a-mouse-event"), null);
assert.equal(parseSgrMouseWheel("\u001B[<0;67;2M"), null);

assert.equal(isSgrMouseInput("\u001B[<0;67;2M"), true);
assert.equal(isSgrMouseInput("[<0;67;2M"), true);
assert.equal(isSgrMouseInput("\u001B[M !!"), true);
assert.equal(isSgrMouseInput("\u001B[<64;67;2M\u001B[<64;67;2M"), true);
assert.equal(isSgrMouseInput("hello"), false);

assert.equal(
  findTranscriptMouseHit({
    click: { x: 67, y: 2 },
    transcriptTop: 1,
    transcriptLeft: 1,
    hitAreas: showMoreHitAreas,
  }),
  "thinking-1",
);

assert.equal(
  findTranscriptMouseHit({
    click: { x: 66, y: 2 },
    transcriptTop: 1,
    transcriptLeft: 1,
    hitAreas: showMoreHitAreas,
  }),
  null,
);

assert.equal(
  findTranscriptMouseHit({
    click: { x: 67, y: 3 },
    transcriptTop: 1,
    transcriptLeft: 1,
    hitAreas: showMoreHitAreas,
  }),
  null,
);

assert.equal(
  findTranscriptMouseHit({
    click: { x: 67, y: 2 },
    transcriptTop: 1,
    transcriptLeft: 1,
    hitAreas: [],
  }),
  null,
);
