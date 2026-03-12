"""
Command Picker for Telegram Bot
Provides inline keyboard interface for selecting Claude Code slash commands.
"""

from typing import List, Tuple, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# Priority commands shown first (before categories)
PRIORITY_COMMANDS = [
    ("autopilot", "/oh-my-claudecode:autopilot", "Full autonomous execution"),
    ("ralplan", "/oh-my-claudecode:ralplan", "Iterative planning loop"),
    ("research", "/oh-my-claudecode:research", "Deep research mode"),
]


# Built-in command categories
COMMAND_CATEGORIES = [
    {
        "name": "OMC",
        "icon": "🔧",
        "description": "oh-my-claudecode commands",
        "commands": [
            ("autopilot", "/oh-my-claudecode:autopilot", "Autonomous execution"),
            ("plan", "/oh-my-claudecode:plan", "Planning session"),
            ("architect", "/oh-my-claudecode:architect", "Architecture advisor"),
            ("analyst", "/oh-my-claudecode:analyst", "Requirements analysis"),
            ("critic", "/oh-my-claudecode:critic", "Critical review"),
            ("executor", "/oh-my-claudecode:executor", "Implementation"),
            ("review", "/oh-my-claudecode:review", "Code review"),
            ("cancel", "/oh-my-claudecode:cancel", "Cancel active mode"),
            ("help", "/oh-my-claudecode:help", "Show help"),
        ]
    },
    {
        "name": "Workflow",
        "icon": "🚀",
        "description": "Development workflow",
        "commands": [
            ("fullcycle", "/fullcycle", "Full dev cycle"),
            ("기획", "/기획", "Planning phase"),
            ("구현", "/구현", "Implementation"),
            ("안정화", "/안정화", "Stabilization"),
            ("배포", "/배포", "Deployment"),
        ]
    },
    {
        "name": "Git",
        "icon": "📦",
        "description": "Git commands",
        "commands": [
            ("commit", "/commit", "Create commit"),
            ("pr", "/pr", "Create PR"),
        ]
    },
    {
        "name": "Session",
        "icon": "💬",
        "description": "Session management",
        "commands": [
            ("clear", "/clear", "Clear context"),
            ("compact", "/compact", "Compact history"),
            ("help", "/help", "Show help"),
        ]
    },
]


def build_flat_commands_keyboard() -> InlineKeyboardMarkup:
    """Build flat keyboard with priority commands at TOP (for instant access)."""
    buttons = []

    # 🚀 Priority commands at TOP (most used - instant access)
    for name, full_cmd, desc in PRIORITY_COMMANDS:
        btn = InlineKeyboardButton(
            text=f"⭐ {name}",
            switch_inline_query_current_chat=full_cmd + " "
        )
        buttons.append([btn])

    # Separator
    buttons.append([InlineKeyboardButton("─── 📂 More Commands ───", callback_data="cmd:noop")])

    # Other commands after (less used)
    for category in COMMAND_CATEGORIES:
        icon = category["icon"]
        for cmd_name, full_cmd, desc in category["commands"]:
            # Skip if already in priority
            if any(full_cmd == pc[1] for pc in PRIORITY_COMMANDS):
                continue
            btn = InlineKeyboardButton(
                text=f"{icon} {cmd_name}",
                switch_inline_query_current_chat=full_cmd + " "
            )
            buttons.append([btn])

    # Close button at very bottom
    buttons.append([
        InlineKeyboardButton("❌ Close", callback_data="cmd:x")
    ])

    return InlineKeyboardMarkup(buttons)


def build_category_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard showing command categories."""
    buttons = []
    row = []

    for idx, cat in enumerate(COMMAND_CATEGORIES):
        btn = InlineKeyboardButton(
            text=f"{cat['icon']} {cat['name']}",
            callback_data=f"cmd:cat:{idx}"
        )
        row.append(btn)

        # 3 buttons per row
        if len(row) == 3:
            buttons.append(row)
            row = []

    # Add remaining buttons
    if row:
        buttons.append(row)

    # Cancel button
    buttons.append([
        InlineKeyboardButton("❌ Cancel", callback_data="cmd:x")
    ])

    return InlineKeyboardMarkup(buttons)


def build_commands_keyboard(category_idx: int) -> Optional[InlineKeyboardMarkup]:
    """Build inline keyboard showing commands in a category."""
    if category_idx < 0 or category_idx >= len(COMMAND_CATEGORIES):
        return None

    category = COMMAND_CATEGORIES[category_idx]
    buttons = []
    row = []

    for cmd_idx, (name, _, desc) in enumerate(category["commands"]):
        btn = InlineKeyboardButton(
            text=name,
            callback_data=f"cmd:run:{category_idx}:{cmd_idx}"
        )
        row.append(btn)

        # 2 buttons per row (commands are longer)
        if len(row) == 2:
            buttons.append(row)
            row = []

    # Add remaining buttons
    if row:
        buttons.append(row)

    # Navigation buttons
    buttons.append([
        InlineKeyboardButton("◀️ Back", callback_data="cmd:back"),
        InlineKeyboardButton("❌ Cancel", callback_data="cmd:x")
    ])

    return InlineKeyboardMarkup(buttons)


def get_command(category_idx: int, cmd_idx: int) -> Optional[Tuple[str, str, str]]:
    """Get command tuple (name, full_command, description) by indices."""
    if category_idx < 0 or category_idx >= len(COMMAND_CATEGORIES):
        return None

    category = COMMAND_CATEGORIES[category_idx]
    commands = category["commands"]

    if cmd_idx < 0 or cmd_idx >= len(commands):
        return None

    return commands[cmd_idx]


def get_category_name(category_idx: int) -> str:
    """Get category name by index."""
    if category_idx < 0 or category_idx >= len(COMMAND_CATEGORIES):
        return "Unknown"
    return COMMAND_CATEGORIES[category_idx]["name"]
