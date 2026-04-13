"""This module provides a function to create spinners and loaders in the current UI context."""
from nicegui import ui


def create_overlay_spinner(message: str | None = None) -> ui.dialog:
    """
    Create a full-screen overlay spinner with an optional message.

    This implementation uses ui.dialog to ensure the spinner is positioned
    relative to the viewport, breaking out of any parent CSS transform contexts.

    Args:
        message (str | None, optional): A text message to display above the spinner. Defaults to None.

    Returns:
        ui.dialog: A NiceGUI dialog element representing the overlay spinner.
    """
    dialog = ui.dialog().props(
        "persistent maximized transition-show=fade transition-hide=fade"
    )

    # Use a full-screen semi-transparent card to show the overlay look
    with (
        dialog,
        ui.card().classes(
            "items-center justify-center bg-black/40 w-full h-full rounded-none shadow-none"
        ),
    ):
        with ui.column().classes("items-center"):
            if message:
                ui.label(message).classes("text-white text-lg mb-4")
            ui.spinner(size="64px", color="#ffffff")

    dialog.open()
    return dialog


def create_loader(message: str | None = None) -> ui.element:
    """
    Create an inline loader spinner with an optional message.

    This loader appears as a row with a "dots"-style spinner and a label,
    suitable for use inside components where local loading feedback is needed.

    Args:
        message (str | None, optional): A message to display next to the spinner. Defaults to None.

    Returns:
        ui.element: A NiceGUI element representing the inline loader.
    """

    with ui.row().classes("items-center") as loader:
        ui.spinner(type="dots", size="lg")
        if message:
            ui.label(message).classes("text-lg ml-2")

    return loader
