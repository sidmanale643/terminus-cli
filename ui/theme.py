COLORS = {
    "accent": "#EF4444",
    "accent_alt": "#DC2626",
    "text": "#E5E7EB",
    "muted": "#9CA3AF",
    "subtle": "#64748B",
    "border": "#374151",
    "selection": "#7F1D1D",
    "selection_text": "#FEE2E2",
    "success": "#34D399",
    "warning": "#FBBF24",
    "danger": "#EF4444",
}


def create_progress_bar(
    context_percent: float, bar_width: int = 25, colors: dict = None
):
    c = colors or COLORS
    filled = int((context_percent / 100) * bar_width)
    bar = "█" * filled + "·" * (bar_width - filled)

    if context_percent < 50:
        color = c["success"]
    elif context_percent < 80:
        color = c["warning"]
    else:
        color = c["danger"]

    return bar, color


def get_role_color(role: str) -> str:
    role_colors = {
        "system": COLORS["subtle"],
        "user": COLORS["accent_alt"],
        "assistant": COLORS["text"],
        "tool": COLORS["warning"],
    }
    return role_colors.get(role.lower(), COLORS["text"])
