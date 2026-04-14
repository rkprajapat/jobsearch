# UI utility functions for common operations

from ui.constants import CONTENT

_PREVIEW_LENGTH: int = int(CONTENT["description_preview_length"])


def truncate_text(text: str, max_length: int = _PREVIEW_LENGTH) -> tuple[str, bool]:
    """
    Truncate text if it exceeds max length.

    Returns:
        tuple[str, bool]: (truncated_text, was_truncated)
    """
    if len(text) > max_length:
        return text[:max_length] + "...", True
    return text, False


class DescriptionToggle:
    """Manages state for expandable description text."""

    def __init__(self, full_text: str, max_length: int = _PREVIEW_LENGTH):
        self.full_text = full_text
        self.max_length = max_length
        self.is_expanded = False
        self.preview_text = truncate_text(full_text, max_length)[0]

    def get_current_text(self) -> str:
        """Get current text state."""
        return self.full_text if self.is_expanded else self.preview_text

    def get_button_label(self) -> str:
        """Get current button label."""
        return str(
            CONTENT["button_show_less"]
            if self.is_expanded
            else CONTENT["button_show_more"]
        )

    def toggle(self) -> tuple[str, str]:
        """
        Toggle expansion state.

        Returns:
            tuple[str, str]: (new_text, new_button_label)
        """
        self.is_expanded = not self.is_expanded
        return self.get_current_text(), self.get_button_label()


def format_label(template: str, **kwargs) -> str:
    """Format a label template with values."""
    return template.format(**kwargs)
