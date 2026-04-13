"""
Applications management UI for tracking job opportunities and application status.
"""
from nicegui import ui, run
import humanize
import traceback
import asyncio

from models.opportunity import Opportunity, load_opportunities
from ui.spinners import create_overlay_spinner
from ui.constants import CLASSES, LAYOUT, CONTENT, SWITCH_PROPS, BUTTON_PROPS
from ui.application_state import ApplicationStateManager
from ui.utils import DescriptionToggle, format_label
from agents.resume_builder.agent import ResumeAgent


async def show_opportunities() -> None:
    """Display list of all opportunities with application status tracking."""
    spinner = create_overlay_spinner(CONTENT["spinner_loading_msg"])
    try:
        opportunities = await run.io_bound(load_opportunities)
        if not opportunities:
            ui.notify(CONTENT["warning_no_opportunities"], type="warning")
            return
        
        state_manager = ApplicationStateManager(opportunities)
        
        # Header section
        _render_header()
        
        # Summary statistics
        summary_labels = _render_summary(state_manager)
        
        # Register callback for state updates
        state_manager.on_state_changed(
            lambda: _update_summary(summary_labels, state_manager)
        )
        
        # Render opportunities
        sorted_opps = state_manager.get_sorted_opportunities()
        filtered_opps = state_manager.filter_complete_opportunities(sorted_opps)
        
        for opp in filtered_opps:
            await _render_opportunity_card(opp, state_manager)
    
    except Exception as e:
        ui.notify(format_label(CONTENT["error_loading"], e=e), type="negative") # type: ignore
        traceback.print_exc()
    finally:
        spinner.delete()


def _render_header() -> None:
    """Render page header with title and back button."""
    with ui.row().classes(LAYOUT["header_row"]):
        ui.label("Applications").classes(CLASSES["page_title"])
        ui.button(
            CONTENT["button_back"], # type: ignore
            on_click=lambda: ui.navigate.back(),
            icon="arrow_back",
        ).props(BUTTON_PROPS["back"]).classes(CLASSES["button_outline"])


def _render_summary(state_manager: ApplicationStateManager) -> dict:
    """
    Render summary statistics section.
    
    Returns:
        dict: Labels for updating summary counts
    """
    with ui.row().classes(LAYOUT["summary_row"]):
        total_label = ui.label(
            format_label(CONTENT["label_total"], count=len(state_manager.opportunities)) # type: ignore
        ).classes(CLASSES["stat_label_neutral"])
        
        applied_label = ui.label(
            format_label(CONTENT["label_applied"], count=state_manager.get_applied_count()) # type: ignore
        ).classes(CLASSES["stat_label_positive"])
        
        not_applied_label = ui.label(
            format_label(CONTENT["label_not_applied"], count=state_manager.get_not_applied_count()) # type: ignore
        ).classes(CLASSES["stat_label_negative"])
    
    return {
        "total": total_label,
        "applied": applied_label,
        "not_applied": not_applied_label,
    }


def _update_summary(labels: dict, state_manager: ApplicationStateManager) -> None:
    """Update summary labels with current counts."""
    labels["applied"].text = format_label(
        CONTENT["label_applied"], count=state_manager.get_applied_count() # type: ignore
    )
    labels["not_applied"].text = format_label(
        CONTENT["label_not_applied"], count=state_manager.get_not_applied_count() # type: ignore
    )


async def _render_opportunity_card(
    opp: Opportunity, 
    state_manager: ApplicationStateManager
) -> None:
    """Render a single opportunity card with interactive controls."""
    async def on_relevant_change(event, current_opp=opp):
        """Handle relevant status toggle."""
        success = await state_manager.update_relevant_status(current_opp, bool(event.value))
        if not success:
            ui.notify(CONTENT["error_save_failed"], type="negative")
    
    async def on_applied_change(event, current_opp=opp):
        """Handle applied status toggle."""
        success = await state_manager.update_applied_status(current_opp, bool(event.value))
        if not success:
            ui.notify(CONTENT["error_save_failed"], type="negative")
    
    with ui.card().classes(CLASSES["card_container"]):
        # Card header with title and controls
        with ui.row().classes(LAYOUT["card_header"]):
            with ui.column().classes(LAYOUT["card_column_left"]):
                ui.link(
                    text=opp.designation or "",
                    target=opp.source_url or "",
                    new_tab=True
                ).classes(CLASSES["card_title"])
            
            # Status switches
            with ui.column().classes(LAYOUT["card_column_right"]):
                with ui.column().classes(LAYOUT["switches_column"]):
                    ui.switch(
                        CONTENT["switch_relevant"], # type: ignore
                        value=bool(opp.relevant),
                        on_change=on_relevant_change
                    ).props(SWITCH_PROPS["relevant"])
                    
                    ui.switch(
                        CONTENT["switch_applied"], # type: ignore
                        value=opp.applied,
                        on_change=on_applied_change
                    ).props(SWITCH_PROPS["applied"])
        
        # Company and location info
        ui.label(format_label(CONTENT["label_company"], name=opp.company_name)).classes(CLASSES["card_meta"]) # type: ignore
        ui.label(format_label(CONTENT["label_location"], location=opp.location)).classes(CLASSES["card_meta"]) # type: ignore
        
        # Posted date
        if opp.date_posted:
            posted_date = humanize.naturaldate(opp.date_posted)
            ui.label(format_label(CONTENT["label_posted"], date=posted_date)).classes(CLASSES["card_meta"]) # type: ignore
        
        # Job description with toggle
        if opp.job_description:
            _render_description(opp.job_description)
        
        # Action button
        ui.button(
            CONTENT["button_prepare_app"], # type: ignore
            on_click=lambda: _prepare_application(opp)
        ).props(BUTTON_PROPS["prepare"]).classes(CLASSES["button_secondary"])

async def _prepare_application(opp: Opportunity) -> None:
    """Prepare tailored resume and cover letter for the opportunity."""
    print(f"Preparing application for: {opp.designation} at {opp.company_name}: ({opp.job_description[:100]}...)")  # Debug log

    if not opp.job_description:
        ui.notify("No job description available to tailor application.", type="warning")
        return

    spinner = create_overlay_spinner('Preparing tailored resume and cover letter...')
    try:
        resume_agent = ResumeAgent()
        tailored_resume = await run.cpu_bound(resume_agent.prepare_resume, opp.job_description)
        ui.notify("Tailored resume and cover letter prepared successfully.")
    except Exception as e:
        ui.notify(f"Failed to prepare application: {e}", type="negative")
    finally:
        spinner.delete()


def _render_description(job_description: str) -> None:
    """Render expandable job description."""
    description_toggle = DescriptionToggle(job_description)
    
    with ui.column().classes(LAYOUT["description_column"]):
        desc_label = ui.markdown(description_toggle.get_current_text()).classes(CLASSES["card_meta"])
        
        # Only show toggle button if description needs truncation
        if len(job_description) > int(CONTENT["description_preview_length"]):
            toggle_button = ui.button(
                description_toggle.get_button_label(),
                on_click=lambda: _toggle_description(desc_label, toggle_button, description_toggle)
            ).props(BUTTON_PROPS["toggle"]).classes(CLASSES["toggle_button"])


def _toggle_description(label, button, toggle_state: DescriptionToggle) -> None:
    """Toggle job description expansion."""
    new_text, new_button_label = toggle_state.toggle()
    label.content = new_text
    button.text = new_button_label