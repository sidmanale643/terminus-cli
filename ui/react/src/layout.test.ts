import assert from "node:assert/strict";
import {
  calculateBottomWorkerPaneHeight,
  calculateMainContentRows,
  calculateSideBySideHeight,
  calculateSideWorkerPaneHeight,
  calculateTranscriptFrameHeight,
  calculateTranscriptHeight,
  calculateWorkerPaneLayout,
} from "./layout.js";

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: true,
    renderedTranscriptRows: 20,
    hasWorkers: false,
    hasTodos: false,
    isGenerating: false,
  }),
  13,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: false,
    renderedTranscriptRows: 1,
    hasWorkers: false,
    hasTodos: false,
    isGenerating: false,
  }),
  3,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: false,
    renderedTranscriptRows: 0,
    hasWorkers: false,
    hasTodos: false,
    isGenerating: false,
  }),
  0,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: false,
    renderedTranscriptRows: 100,
    hasWorkers: false,
    hasTodos: false,
    isGenerating: false,
  }),
  26,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 20,
    showIntro: true,
    renderedTranscriptRows: 20,
    hasWorkers: true,
    workerPaneRows: 8,
    hasTodos: false,
    isGenerating: true,
  }),
  0,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 32,
    showIntro: false,
    renderedTranscriptRows: 100,
    hasWorkers: true,
    workerPaneRows: 10,
    hasTodos: false,
    isGenerating: false,
  }),
  16,
);

assert.equal(
  calculateTranscriptHeight({
    terminalHeight: 10,
    showIntro: false,
    renderedTranscriptRows: 100,
    hasWorkers: false,
    hasTodos: false,
    isGenerating: false,
  }),
  4,
);

const wideWorkerLayout = calculateWorkerPaneLayout({
  terminalWidth: 130,
  terminalHeight: 32,
  hasWorkers: true,
  workerCount: 3,
});
assert.equal(wideWorkerLayout.placement, "side");
assert.equal(wideWorkerLayout.paneRows, 0);
assert.equal(wideWorkerLayout.transcriptWidth + wideWorkerLayout.paneWidth, 130);

const narrowWorkerLayout = calculateWorkerPaneLayout({
  terminalWidth: 90,
  terminalHeight: 32,
  hasWorkers: true,
  workerCount: 2,
});
assert.equal(narrowWorkerLayout.placement, "bottom");
assert.equal(narrowWorkerLayout.paneRows, 10);
assert.equal(narrowWorkerLayout.transcriptWidth, 90);

const sideMainContentRows = calculateMainContentRows({
  terminalHeight: 32,
  bannerRows: 0,
  welcomeRows: 0,
  todoPanelRows: 0,
  isGenerating: true,
});
const sideTranscriptHeight = calculateTranscriptFrameHeight({
  mainContentRows: sideMainContentRows,
  renderedTranscriptRows: 40,
  bottomWorkerPaneRows: 0,
});
const sideWorkerPaneHeight = calculateSideWorkerPaneHeight({
  mainContentRows: sideMainContentRows,
  transcriptHeight: sideTranscriptHeight,
  maxWorkerPaneRows: 14,
});
assert.equal(calculateSideBySideHeight(sideTranscriptHeight, sideWorkerPaneHeight, sideMainContentRows), 25);
assert.equal(sideTranscriptHeight + 6 + 1, 32);

const bottomMainContentRows = calculateMainContentRows({
  terminalHeight: 24,
  bannerRows: 0,
  welcomeRows: 0,
  todoPanelRows: 0,
  isGenerating: false,
});
const bottomWorkerPaneHeight = calculateBottomWorkerPaneHeight(narrowWorkerLayout.paneRows, bottomMainContentRows);
const bottomTranscriptHeight = calculateTranscriptFrameHeight({
  mainContentRows: bottomMainContentRows,
  renderedTranscriptRows: 100,
  bottomWorkerPaneRows: bottomWorkerPaneHeight,
});
assert.equal(bottomTranscriptHeight + bottomWorkerPaneHeight + 6, 24);

const stableSideWorkerPaneHeight = calculateSideWorkerPaneHeight({
  mainContentRows: sideMainContentRows,
  transcriptHeight: calculateTranscriptFrameHeight({
    mainContentRows: sideMainContentRows,
    renderedTranscriptRows: 4,
    bottomWorkerPaneRows: 0,
  }),
  maxWorkerPaneRows: 14,
});
assert.equal(stableSideWorkerPaneHeight, 14);
assert.equal(
  calculateSideWorkerPaneHeight({
    mainContentRows: sideMainContentRows,
    transcriptHeight: calculateTranscriptFrameHeight({
      mainContentRows: sideMainContentRows,
      renderedTranscriptRows: 8,
      bottomWorkerPaneRows: 0,
    }),
    maxWorkerPaneRows: 14,
  }),
  stableSideWorkerPaneHeight,
);
