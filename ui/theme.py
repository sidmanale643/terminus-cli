COLORS = {
    "background": "#17191A",
    "panel": "#202325",
    "border": "#555B5E",
    "border_hover": "#BCC2C5",
    "text": "#D9DDDF",
    "dim": "#BCC2C5",
    "muted": "#7F878B",
    "subtle": "#7F878B",
    "accent": "#E2382A",
    "accent_alt": "#FF766A",
    "accent_soft": "#FF766A",
    "selection": "#A9251D",
    "selection_text": "#D9DDDF",
    "success": "#75B798",
    "warning": "#D9A441",
    "danger": "#FF5A4D",
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
