export const COLORS = {
  accent: "#EF4444",
  accentAlt: "#DC2626",
  text: "#E5E7EB",
  muted: "#9CA3AF",
  subtle: "#64748B",
  border: "#374151",
  selection: "#7F1D1D",
  selectionText: "#FEE2E2",
  success: "#34D399",
  warning: "#FBBF24",
  danger: "#EF4444",
};

export function getContextColor(percent: number): string {
  if (percent < 50) return COLORS.success;
  if (percent < 80) return COLORS.warning;
  return COLORS.danger;
}

export function createProgressBar(percent: number, width = 25): string {
  const filled = Math.floor((percent / 100) * width);
  return "█".repeat(filled) + "·".repeat(width - filled);
}
