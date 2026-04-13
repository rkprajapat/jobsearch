from nicegui import app, ui

from ui.jd_extraction import extraction_page


def _inject_theme() -> None:
    ui.add_head_html(
        '''
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
        '''
    )


@ui.page('/')
def main_page():
    _inject_theme()

    with ui.column().classes('w-full min-h-screen items-center px-4 py-8 md:py-12'):
        with ui.column().classes('w-full max-w-5xl gap-6 md:gap-8'):
            with ui.column().classes('glass-card p-6 md:p-10'):
                ui.label('Job Search Control Center').classes('brand-title text-3xl md:text-5xl font-extrabold text-slate-800')
                ui.label('Automate extraction, monitor pipeline runs, and review application readiness from one place.').classes('text-base md:text-lg text-slate-600 mt-2')

                with ui.row().classes('mt-6 gap-3 flex-wrap'):
                    ui.button('Open Extraction Studio', on_click=lambda: ui.navigate.to('/extraction'), icon='rocket_launch').classes('bg-teal-700 text-white px-5 py-3 rounded-xl')
                    ui.button('Open Application Workspace', on_click=lambda: ui.navigate.to('/application'), icon='work').classes('bg-amber-600 text-white px-5 py-3 rounded-xl')


@ui.page('/extraction')
def extraction():
    _inject_theme()
    extraction_page()

@ui.page('/application')
def application():
    _inject_theme()

    with ui.column().classes('w-full min-h-screen items-center px-4 py-8'):
        with ui.column().classes('w-full max-w-5xl gap-5'):
            with ui.row().classes('w-full items-center justify-between flex-wrap gap-3'):
                with ui.column().classes('gap-0'):
                    ui.label('Application Workspace').classes('brand-title text-3xl font-extrabold text-slate-800')
                    ui.label('Plan your next 7 days of applications with focus and consistency.').classes('text-slate-600')
                ui.button('Back to Dashboard', on_click=lambda: ui.navigate.to('/'), icon='arrow_back').props('outline').classes('border-slate-300 text-slate-700')

            with ui.row().classes('w-full gap-4 flex-wrap md:flex-nowrap'):
                with ui.column().classes('glass-card p-5 flex-1 min-w-[260px]'):
                    ui.label('Today').classes('text-lg font-bold text-slate-800')
                    ui.label('No pending application actions configured yet.').classes('text-slate-600 mt-1')
                    ui.button('Add Task (Soon)', icon='add_task').props('flat').classes('text-teal-700 mt-2')

                with ui.column().classes('glass-card p-5 flex-1 min-w-[260px]'):
                    ui.label('This Week').classes('text-lg font-bold text-slate-800')
                    ui.label('Build a shortlist from extracted roles and prioritize high-fit opportunities first.').classes('text-slate-600 mt-1')
                    ui.button('Open Extraction Studio', on_click=lambda: ui.navigate.to('/extraction'), icon='insights').classes('bg-teal-700 text-white mt-2')

def start_web_ui():
    ui.run(title="Job Search Dashboard")