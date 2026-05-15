import assert from "node:assert/strict";
import { calculateTranscriptHeight } from "./layout.js";

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: true,
    hasWorkers: false,
    isGenerating: false,
  }),
  13,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: false,
    hasWorkers: false,
    isGenerating: false,
  }),
  26,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 20,
    showIntro: true,
    hasWorkers: true,
    isGenerating: true,
  }),
  6,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: false,
    hasWorkers: true,
    workerBoardExpanded: true,
    isGenerating: false,
  }),
  15,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 10,
    showIntro: false,
    hasWorkers: false,
    isGenerating: false,
  }),
  6,
);
