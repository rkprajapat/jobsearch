# UI Theme & Constants module
from typing import Final

# Tailwind class sets for consistent styling
CLASSES: dict[str, str] = {
    "page_title": "brand-title text-3xl font-extrabold text-slate-800",
    "section_header": "text-lg font-medium",
    "card_container": "w-full glass-card gap-1",
    "card_title": "text-xl font-semibold text-slate-800",
    "card_meta": "text-sm text-slate-600",
    "button_outline": "border-slate-300 text-slate-700 self-end",
    "button_secondary": "self-end text-sm px-3 py-1",
    "toggle_button": "flat dense no-caps self-start text-xs text-blue-600 px-1 py-0",
    "stat_label_neutral": "text-lg font-medium",
    "stat_label_positive": "text-lg font-medium text-green-600",
    "stat_label_negative": "text-lg font-medium text-red-600",
}

# Layout constants
LAYOUT: dict[str, str] = {
    "header_row": "w-full items-center justify-between flex-wrap gap-3 mb-4",
    "summary_row": "gap-6 mb-4",
    "card_header": "w-full items-start justify-between gap-3",
    "card_column_left": "gap-1",
    "card_column_right": "items-end gap-1",
    "switches_column": "items-end gap-3",
    "description_column": "gap-1 mt-3",
}

# Content constants
CONTENT: dict[str, str | int] = {
    "description_preview_length": 200,
    "spinner_loading_msg": "Loading opportunities...",
    "error_save_failed": "Failed to save update.",
    "error_loading": "Error loading opportunities: {e}",
    "warning_no_opportunities": "No opportunities found.",
    "button_prepare_app": "Prepare Application",
    "button_back": "Go Back",
    "button_show_more": "Show more text",
    "button_show_less": "Show less",
    "switch_relevant": "Relevant",
    "switch_applied": "Applied",
    "label_total": "Total Opportunities: {count}",
    "label_applied": "Applied: {count}",
    "label_not_applied": "Not Applied: {count}",
    "label_company": "Company: {name}",
    "label_location": "Location: {location}",
    "label_posted": "Posted: {date}",
}

# Switch props
SWITCH_PROPS = {
    "relevant": "dense color=green",
    "applied": "dense color=green",
}

# Button props
BUTTON_PROPS = {
    "back": "outline",
    "prepare": "outline",
    "toggle": "flat dense no-caps",
}
