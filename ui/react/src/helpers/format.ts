export function formatPrice(value: number): string {
  return value === 0 ? "free" : `$${value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "")}`;
}

export function getMessageColor(type: string): { color: string; dim: boolean } {
  const COLORS = {
    danger: "#EF4444",
    success: "#34D399",
    accentAlt: "#EF4444",
    muted: "#9CA3AF",
    text: "#E5E7EB",
    warning: "#FBBF24",
  };

  switch (type) {
    case "error":
      return { color: COLORS.danger, dim: false };
    case "alert":
      return { color: COLORS.warning, dim: false };
    case "success":
      return { color: COLORS.success, dim: false };
    case "user":
      return { color: COLORS.accentAlt, dim: false };
    case "system":
      return { color: COLORS.muted, dim: true };
    default:
      return { color: COLORS.text, dim: false };
  }
}