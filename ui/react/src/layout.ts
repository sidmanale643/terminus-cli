export interface TranscriptLayoutOptions {
  terminalHeight: number;
  showIntro: boolean;
  renderedTranscriptRows: number;
  hasWorkers: boolean;
  workerPaneRows?: number;
  hasTodos: boolean;
  todoPaneRows?: number;
  isGenerating: boolean;
}

export interface WorkerPaneLayoutOptions {
  terminalWidth: number;
  terminalHeight: number;
  hasWorkers: boolean;
  workerCount: number;
}

export interface MainContentRowsOptions {
  terminalHeight: number;
  bannerRows: number;
  welcomeRows: number;
  todoPanelRows: number;
  isGenerating: boolean;
}

export interface TranscriptFrameHeightOptions {
  mainContentRows: number;
  renderedTranscriptRows: number;
  bottomWorkerPaneRows: number;
}

export interface SideWorkerPaneHeightOptions {
  mainContentRows: number;
  transcriptHeight: number;
  maxWorkerPaneRows: number;
}

export type WorkerPanePlacement = "side" | "bottom";

export interface WorkerPaneLayout {
  placement: WorkerPanePlacement;
  transcriptWidth: number;
  paneWidth: number;
  paneRows: number;
}

const MIN_TRANSCRIPT_WIDTH = 60;
export const TRANSCRIPT_CHROME_ROWS = 2;
const MIN_TRANSCRIPT_CONTENT_ROWS = 1;
const BANNER_LINES = 8;
const WELCOME_LINES = 5;
const COMPOSER_LINES = 6;
const GENERATION_LINES = 1;
const MIN_WORKER_PANE_WIDTH = 38;
const MAX_WORKER_PANE_WIDTH = 52;
const MIN_WORKER_PANE_ROWS = 6;
const MAX_BOTTOM_WORKER_PANE_ROWS = 14;
const SIDE_LAYOUT_MIN_WIDTH = 110;
const SIDE_LAYOUT_MIN_HEIGHT = 22;

export function calculateWorkerPaneLayout(options: WorkerPaneLayoutOptions): WorkerPaneLayout {
  if (!options.hasWorkers) {
    return {
      placement: "bottom",
      transcriptWidth: options.terminalWidth,
      paneWidth: options.terminalWidth,
      paneRows: 0,
    };
  }

  if (canUseSidePaneLayout(options)) {
    const paneWidth = calculateSidePaneWidth(options.terminalWidth);
    return {
      placement: "side",
      transcriptWidth: options.terminalWidth - paneWidth,
      paneWidth,
      paneRows: 0,
    };
  }

  return {
    placement: "bottom",
    transcriptWidth: options.terminalWidth,
    paneWidth: options.terminalWidth,
    paneRows: calculateBottomPaneRows(options.workerCount, options.terminalHeight),
  };
}

export function calculateMainContentRows(options: MainContentRowsOptions): number {
  const reservedRows =
    options.bannerRows +
    options.welcomeRows +
    options.todoPanelRows +
    COMPOSER_LINES +
    (options.isGenerating ? GENERATION_LINES : 0);

  return Math.max(0, options.terminalHeight - reservedRows);
}

export function calculateTranscriptFrameHeight(options: TranscriptFrameHeightOptions): number {
  if (options.renderedTranscriptRows <= 0) {
    return 0;
  }

  const desiredHeight = Math.max(
    TRANSCRIPT_CHROME_ROWS + MIN_TRANSCRIPT_CONTENT_ROWS,
    options.renderedTranscriptRows + TRANSCRIPT_CHROME_ROWS,
  );
  const availableHeight = Math.max(0, options.mainContentRows - options.bottomWorkerPaneRows);

  return Math.min(desiredHeight, availableHeight);
}

export function calculateBottomWorkerPaneHeight(requestedRows: number, mainContentRows: number): number {
  return Math.min(Math.max(0, requestedRows), Math.max(0, mainContentRows));
}

export function calculateSideWorkerPaneHeight(options: SideWorkerPaneHeightOptions): number {
  const stableRows = Math.min(options.maxWorkerPaneRows, options.mainContentRows);
  return Math.min(
    options.mainContentRows,
    Math.max(options.transcriptHeight, stableRows),
  );
}

export function calculateSideBySideHeight(
  transcriptHeight: number,
  workerPaneHeight: number,
  mainContentRows: number,
): number {
  return Math.min(
    Math.max(0, mainContentRows),
    Math.max(transcriptHeight, workerPaneHeight),
  );
}

export function calculateTranscriptHeight(options: TranscriptLayoutOptions): number {
  if (options.renderedTranscriptRows <= 0) {
    return 0;
  }

  const reservedLines =
    (options.showIntro ? BANNER_LINES + WELCOME_LINES : 0) +
    COMPOSER_LINES +
    (options.isGenerating ? GENERATION_LINES : 0) +
    (options.hasWorkers ? options.workerPaneRows ?? 0 : 0) +
    (options.hasTodos ? options.todoPaneRows ?? 0 : 0);

  const desiredHeight = Math.max(
    TRANSCRIPT_CHROME_ROWS + MIN_TRANSCRIPT_CONTENT_ROWS,
    options.renderedTranscriptRows + TRANSCRIPT_CHROME_ROWS,
  );
  const availableHeight = Math.max(0, options.terminalHeight - reservedLines);

  return Math.min(desiredHeight, availableHeight);
}

function canUseSidePaneLayout(options: WorkerPaneLayoutOptions): boolean {
  return (
    options.terminalWidth >= SIDE_LAYOUT_MIN_WIDTH &&
    options.terminalHeight >= SIDE_LAYOUT_MIN_HEIGHT &&
    options.terminalWidth - calculateSidePaneWidth(options.terminalWidth) >= MIN_TRANSCRIPT_WIDTH
  );
}

function calculateSidePaneWidth(terminalWidth: number): number {
  const targetWidth = Math.floor(terminalWidth * 0.36);
  return Math.min(MAX_WORKER_PANE_WIDTH, Math.max(MIN_WORKER_PANE_WIDTH, targetWidth));
}

function calculateBottomPaneRows(workerCount: number, terminalHeight: number): number {
  const targetRows = Math.max(MIN_WORKER_PANE_ROWS, Math.min(MAX_BOTTOM_WORKER_PANE_ROWS, workerCount * 5));
  const maxRows = Math.max(
    MIN_WORKER_PANE_ROWS,
    terminalHeight - COMPOSER_LINES - TRANSCRIPT_CHROME_ROWS - MIN_TRANSCRIPT_CONTENT_ROWS,
  );
  return Math.min(targetRows, maxRows);
}
