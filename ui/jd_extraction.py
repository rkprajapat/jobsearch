import asyncio

from nicegui import run, ui

from services.main import _run_cluster_report, _run_clustering, run_pipeline
from ui.spinners import create_overlay_spinner


async def start_full_extraction():
    spinner = create_overlay_spinner(
        "Starting full extraction. This can take a while..."
    )
    try:
        await run.io_bound(lambda: asyncio.run(run_pipeline(cluster=True)))
        ui.notify("Full extraction completed successfully.", type="positive")
    except Exception as exc:
        ui.notify(f"Full extraction failed: {exc}", type="negative", timeout=7000)
    finally:
        spinner.delete()


async def start_jd_extraction():
    spinner = create_overlay_spinner(
        "Starting JD-only extraction. This is faster but skips some steps..."
    )
    try:
        await run.io_bound(lambda: asyncio.run(run_pipeline(only_jd=True)))
        ui.notify("JD-only extraction completed successfully.", type="positive")
    except Exception as exc:
        ui.notify(f"JD-only extraction failed: {exc}", type="negative", timeout=7000)
    finally:
        spinner.delete()


async def generate_cluster_report():
    spinner = create_overlay_spinner(
        "Generating cluster report. This may take a few moments..."
    )
    try:
        await run.cpu_bound(_run_clustering)
        report_path = await run.cpu_bound(_run_cluster_report)
        if report_path:
            ui.notify("Cluster report generated.", type="positive")
            ui.button(
                "Download Report",
                icon="download",
                on_click=lambda: ui.download.file(report_path),
            ).classes("bg-teal-700 text-white rounded-lg")
        else:
            ui.notify(
                "No report was generated. Check extracted data availability.",
                type="warning",
            )
    except Exception as exc:
        ui.notify(f"Failed to generate report: {exc}", type="negative", timeout=7000)
    finally:
        spinner.delete()


async def extraction_page():
    with ui.column().classes("w-full min-h-screen items-center px-4 py-8"):
        with ui.column().classes("w-full max-w-5xl gap-5"):
            with ui.row().classes(
                "w-full items-center justify-between flex-wrap gap-3"
            ):
                with ui.column().classes("gap-0"):
                    ui.label("Extraction Studio").classes(
                        "brand-title text-3xl font-extrabold text-slate-800"
                    )
                    ui.label(
                        "Run data collection pipelines and generate reports from one focused workspace."
                    ).classes("text-slate-600")
                ui.button(
                    "Go Back",
                    on_click=lambda: ui.navigate.back(),
                    icon="arrow_back",
                ).props("outline").classes("border-slate-300 text-slate-700")

            with ui.row().classes("w-full gap-4 flex-wrap md:flex-nowrap"):
                with ui.column().classes("glass-card p-5 flex-1 min-w-[260px]"):
                    ui.label("Full Extraction").classes(
                        "text-xl font-bold text-slate-800"
                    )
                    ui.label(
                        "Runs complete opportunity discovery, JD extraction, and downstream processing for the latest input config."
                    ).classes("text-slate-600 mt-1")
                    ui.button(
                        "Start Full Run",
                        on_click=start_full_extraction,
                        icon="play_arrow",
                    ).classes("bg-teal-700 text-white mt-3 rounded-lg")

                with ui.column().classes("glass-card p-5 flex-1 min-w-[260px]"):
                    ui.label("JD-Only Extraction").classes(
                        "text-xl font-bold text-slate-800"
                    )
                    ui.label(
                        "Skips observation and extracts only job descriptions for faster refresh cycles. Also clusters job descriptions if last report was done more than 30 days ago. If you still want a fresh report, click on Generate Report after JD Extraction."
                    ).classes("text-slate-600 mt-1")
                    ui.button(
                        "Start JD-Only",
                        on_click=start_jd_extraction,
                        icon="description",
                    ).classes("bg-amber-600 text-white mt-3 rounded-lg")

            with ui.column().classes("glass-card p-5 w-full"):
                ui.label("Cluster Report").classes("text-xl font-bold text-slate-800")
                ui.label(
                    "Generates the latest clustering output and prepares a downloadable PDF report."
                ).classes("text-slate-600 mt-1")
                ui.button(
                    "Generate Report",
                    on_click=generate_cluster_report,
                    icon="auto_graph",
                ).classes("bg-slate-800 text-white mt-3 rounded-lg")

            # Extraction Configuration
            with ui.column().classes("glass-card p-5 w-full"):
                ui.label("Extraction Configuration").classes(
                    "text-xl font-bold text-slate-800"
                )
                ui.button(
                    "Edit Configuration",
                    on_click=lambda: ui.navigate.to("/config"),
                    icon="settings",
                ).classes("bg-blue-600 text-white mt-3 rounded-lg")
