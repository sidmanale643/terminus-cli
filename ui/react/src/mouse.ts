export interface MouseClick {
  x: number;
  y: number;
}

export type MouseWheelDirection = "up" | "down";

export interface MouseWheel {
  x: number;
  y: number;
  direction: MouseWheelDirection;
}

export interface TranscriptHitArea {
  id: string;
  row: number;
  startColumn: number;
  endColumn: number;
}

export interface TranscriptMouseHitOptions {
  click: MouseClick;
  transcriptTop: number;
  transcriptLeft: number;
  hitAreas: TranscriptHitArea[];
}

const sgrMousePattern = /^\u001B?\[<(\d+);(\d+);(\d+)([Mm])$/;
const legacyMousePattern = /^\u001B?\[M(.)(.)(.)$/s;
const sgrMouseChunkPattern = /\u001B?\[<\d+;\d+;\d+[Mm]/g;
const legacyMouseChunkPattern = /\u001B?\[M.../gs;
const scrollButtonStart = 64;
const buttonMask = 3;
const leftButtonCode = 0;
const mouseEnableSequence = "\u001B[?1000h\u001B[?1002h\u001B[?1006h";
const mouseDisableSequence = "\u001B[?1006l\u001B[?1002l\u001B[?1000l";

export function isSgrMouseInput(input: string): boolean {
  if (sgrMousePattern.test(input) || legacyMousePattern.test(input)) return true;
  if (!input) return false;
  return input
    .replace(sgrMouseChunkPattern, "")
    .replace(legacyMouseChunkPattern, "")
    .length === 0;
}

export function parseSgrMouseClick(input: string): MouseClick | null {
  return parseModernMouseClick(input) ?? parseLegacyMouseClick(input);
}

export function parseSgrMouseClicks(input: string): MouseClick[] {
  return parseMouseChunks(input)
    .map((chunk) => parseSgrMouseClick(chunk))
    .filter((click): click is MouseClick => Boolean(click));
}

export function parseSgrMouseWheel(input: string): MouseWheel | null {
  return parseModernMouseWheel(input) ?? parseLegacyMouseWheel(input);
}

export function parseSgrMouseWheels(input: string): MouseWheel[] {
  return parseMouseChunks(input)
    .map((chunk) => parseSgrMouseWheel(chunk))
    .filter((wheel): wheel is MouseWheel => Boolean(wheel));
}

function parseMouseChunks(input: string): string[] {
  return [
    ...input.matchAll(sgrMouseChunkPattern),
    ...input.matchAll(legacyMouseChunkPattern),
  ]
    .sort((left, right) => (left.index ?? 0) - (right.index ?? 0))
    .map((match) => match[0]);
}

function parseModernMouseClick(input: string): MouseClick | null {
  const match = sgrMousePattern.exec(input);
  if (!match) return null;

  const button = Number(match[1]);
  const x = Number(match[2]);
  const y = Number(match[3]);
  const action = match[4];

  if (action !== "M" || isIgnoredButton(button)) return null;
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 1 || y < 1) return null;

  return { x, y };
}

function parseModernMouseWheel(input: string): MouseWheel | null {
  const match = sgrMousePattern.exec(input);
  if (!match) return null;

  const button = Number(match[1]);
  const x = Number(match[2]);
  const y = Number(match[3]);
  const action = match[4];

  if (action !== "M" || !isWheelButton(button)) return null;
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 1 || y < 1) return null;

  return { x, y, direction: wheelDirection(button) };
}

function parseLegacyMouseClick(input: string): MouseClick | null {
  const match = legacyMousePattern.exec(input);
  if (!match) return null;

  const button = match[1].charCodeAt(0) - 32;
  if (isIgnoredButton(button)) return null;

  return {
    x: match[2].charCodeAt(0) - 32,
    y: match[3].charCodeAt(0) - 32,
  };
}

function parseLegacyMouseWheel(input: string): MouseWheel | null {
  const match = legacyMousePattern.exec(input);
  if (!match) return null;

  const button = match[1].charCodeAt(0) - 32;
  if (!isWheelButton(button)) return null;

  return {
    x: match[2].charCodeAt(0) - 32,
    y: match[3].charCodeAt(0) - 32,
    direction: wheelDirection(button),
  };
}

function isIgnoredButton(button: number): boolean {
  return button >= scrollButtonStart || (button & buttonMask) !== leftButtonCode;
}

function isWheelButton(button: number): boolean {
  return button >= scrollButtonStart;
}

function wheelDirection(button: number): MouseWheelDirection {
  return (button & 1) === 0 ? "up" : "down";
}

export function findTranscriptMouseHit(options: TranscriptMouseHitOptions): string | null {
  const localRow = options.click.y - options.transcriptTop + 1;
  const localColumn = options.click.x - options.transcriptLeft + 1;

  const hitArea = options.hitAreas.find((area) => (
    area.row === localRow &&
    localColumn >= area.startColumn &&
    localColumn <= area.endColumn
  ));

  return hitArea?.id ?? null;
}

export function enableSgrMouseReporting(stdout: NodeJS.WriteStream | undefined): () => void {
  const output = stdout ?? process.stdout;
  if (!output?.write) return () => {};

  output.write(mouseEnableSequence);
  return () => {
    output.write(mouseDisableSequence);
  };
}
