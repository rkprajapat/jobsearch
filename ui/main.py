from nicegui import ui

from ui.extraction_config import render_config
from ui.jd_extraction import extraction_page
from ui.applications import show_opportunities


def _inject_theme() -> None:
    ui.add_head_html("""
        <style>
            @import url("https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Space+Grotesk:wght@500;700&display=swap");

            :root {
                --surface: #f8f6f1;
                --card: #ffffff;
                --ink: #182026;
                --muted: #5d6872;
                --accent: #0f766e;
                --accent-soft: #d7f4f1;
                --warm: #d97706;
                --radius: 20px;
            }

            body {
                font-family: "Sora", sans-serif;
                background:
                    radial-gradient(circle at 10% 15%, rgba(15, 118, 110, 0.12) 0%, rgba(15, 118, 110, 0) 28%),
                    radial-gradient(circle at 90% 82%, rgba(217, 119, 6, 0.12) 0%, rgba(217, 119, 6, 0) 30%),
                    var(--surface);
            }

            .brand-title {
                font-family: "Space Grotesk", sans-serif;
                letter-spacing: 0.4px;
            }

            .glass-card {
                background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(255,255,255,0.9));
                border: 1px solid rgba(24, 32, 38, 0.08);
                border-radius: var(--radius);
                box-shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
            }

            .feature-icon {
                width: 44px;
                height: 44px;
                border-radius: 12px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-soft);
                color: var(--accent);
                font-size: 1.2rem;
                margin-bottom: 10px;
            }
        </style>
        """)


@ui.page("/")
def main_page():
    _inject_theme()

    with ui.column().classes("w-full min-h-screen items-center px-4 py-8 md:py-12"):
        with ui.column().classes("w-full max-w-5xl gap-6 md:gap-8"):
            with ui.column().classes("glass-card p-6 md:p-10"):
                ui.label("Job Search Control Center").classes(
                    "brand-title text-3xl md:text-5xl font-extrabold text-slate-800"
                )
                ui.label(
                    "Automate extraction, monitor pipeline runs, and review application readiness from one place."
                ).classes("text-base md:text-lg text-slate-600 mt-2")

                with ui.row().classes("mt-6 gap-3 flex-wrap"):
                    ui.button(
                        "Open Extraction Studio",
                        on_click=lambda: ui.navigate.to("/extraction"),
                        icon="rocket_launch",
                    ).classes("bg-teal-700 text-white px-5 py-3 rounded-xl")
                    ui.button(
                        "Open Application Workspace",
                        on_click=lambda: ui.navigate.to("/application"),
                        icon="work",
                    ).classes("bg-amber-600 text-white px-5 py-3 rounded-xl")


@ui.page("/extraction")
async def extraction():
    _inject_theme()
    await extraction_page()


@ui.page("/config")
async def config_page():
    _inject_theme()
    await render_config()


@ui.page("/application")
async def application():
    _inject_theme()

    await show_opportunities()

def start_web_ui():
    ui.run(title="Job Search Dashboard")
