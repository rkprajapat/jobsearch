import json
from pathlib import Path

from nicegui import run, ui

config_dir = Path(__file__).parent.parent.absolute().joinpath("configs")
print("Looking for config in", config_dir)
config_file = config_dir.joinpath("inputs.json").absolute()


def load_config() -> dict | None:
    try:
        if not config_file.exists():
            print("Configuration file not found.", config_file)
            return None

        with open(config_file, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return {}


def save_config(config: dict) -> bool:
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving configuration: {e}")
        return False


async def render_chips(config: dict, config_key: str, description: str = ""):
    chip_values = config.get(config_key, [])
    display_name = config_key.replace("_", " ").capitalize()

    async def on_chip_update(e):
        updated_chip_values = []
        for v in e.value or []:
            if isinstance(v, str):
                normalized_v = v.strip()
                if normalized_v and normalized_v not in updated_chip_values:
                    updated_chip_values.append(normalized_v)

        if not updated_chip_values:
            ui.notify("Value is empty or already added.", type="warning")
            return

        chip_values.clear()
        chip_values.extend(updated_chip_values)
        config[config_key] = chip_values
        if await run.io_bound(save_config, config):
            ui.notify(f"{display_name} updated.", type="positive")
        else:
            ui.notify(
                "Failed to save configuration. Please check the logs.", type="negative"
            )

    # show chip_values as badges
    ui.label(f"{display_name.title()}").classes("text-xl font-bold text-slate-800 mt-4")
    if description:
        ui.label(description).classes("text-slate-600 text-sm mt-1")
    ui.input_chips(value=chip_values, on_change=on_chip_update).classes("w-full mt-1")


async def render_number_input(config: dict, config_key: str, description: str):
    value = config.get(config_key, 0)
    display_name = config_key.replace("_", " ").capitalize()

    async def on_value_change():
        try:
            if await run.io_bound(save_config, config):
                ui.notify(f"{display_name} updated.", type="positive")
            else:
                ui.notify(
                    "Failed to save configuration. Please check the logs.",
                    type="negative",
                )
        except ValueError:
            ui.notify("Please enter a valid number.", type="warning")

    ui.label(display_name.title()).classes("text-xl font-bold text-slate-800 mt-4")
    ui.label(description).classes("text-slate-600 text-sm mt-1")

    with ui.row().classes("gap-2 items-center"):
        ui.number(value=value).classes("mt-1").bind_value(config, config_key)
        ui.button(icon="save", on_click=on_value_change).classes(
            "bg-blue-600 text-white rounded-lg"
        )


async def render_config():
    config: dict | None = await run.io_bound(load_config)
    if not isinstance(config, dict):
        ui.label(
            "No configuration available. Please check the logs for details."
        ).classes("text-red-600")
        return

    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3 mb-4"):
        ui.label("Extraction Configuration").classes(
            "brand-title text-3xl font-extrabold text-slate-800"
        )
        ui.button(
            "Go Back",
            on_click=lambda: ui.navigate.back(),
            icon="arrow_back",
        ).props("outline").classes("border-slate-300 text-slate-700 self-end")

    await render_chips(config, "skills")
    await render_chips(config, "scope")
    await render_chips(config, "preferred_locations")
    await render_number_input(
        config,
        "jobs_per_source",
        "This is maximum number of opportunities to extract during a full extraction run. Avoid keeping it a large number to prevent automation detection and potential blocking from job boards.",
    )
    await render_number_input(
        config,
        "max_pages",
        "Number of pages to scrape per source during extraction. Adjust based on how many results you want and the structure of the job board (some have more results per page than others).",
    )
    await render_number_input(
        config,
        "login_wait_seconds",
        "Number of seconds to wait for manual login during extraction. Set this to a higher value if you have multi-factor authentication or need extra time to complete login.",
    )
    await render_chips(
        config,
        "stopwords",
        "Words to ignore during JD clustering and report creation. This can help improve the quality of clusters by removing common but uninformative words.",
    )


if __name__ == "__main__":
    print(load_config())
