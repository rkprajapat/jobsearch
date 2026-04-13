# JobSearch

Automates job opportunity collection and post-processing for LinkedIn-based searches, including:
- scraping opportunities,
- extracting job descriptions,
- clustering JD content,
- generating a cluster PDF report.

## Prerequisites

- Python 3.14+
- `uv` package manager
- Valid LinkedIn credentials

## Installation

1. Create and sync dependencies:

```bash
uv sync
```

2. If needed, install the spaCy model explicitly:

```bash
uv add "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
```

## Environment Variables

Create a `.env` file in the project root with:

```env
LINKEDIN_EMAIL=your_email
LINKEDIN_PASSWORD=your_password
DATA_DIR_PATH=./project_data
```

Notes:
- `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` are required.
- `DATA_DIR_PATH` is required and this is where the generated output will be stored

## Configuration (`configs/inputs.json`)

The pipeline reads runtime options from `configs/inputs.json`.

### Current values

- `skills`: keyword list used for role matching/filtering.
	- Current values include: `machine learning`, `data science`, `artificial intelligence`, `neural networks`, `deep learning`, `natural language processing`, `large language models`, `agentic`, `agents`, `engineering`, `architect`, `architecture`.
- `scope`: seniority keywords.
	- Current values: `director`, `head`, `vice president`, `chief`, `lead`, `leader`.
- `preferred_locations`: allowed location terms.
	- Current values: `india`, `usa`, `europe`, `uae`, `canada`, `australia`, `netherlands`, `singapore`, `remote`, `hybrid`.
- `sources`: source URLs to crawl.
	- Current value: `https://www.linkedin.com/jobs/`.
- `jobs_per_source`: number of opportunities collected per source.
	- Current value: `50`.
- `max_pages`: max pages visited per source.
	- Current value: `5`.
- `headless`: whether browser runs in headless mode.
	- Current value: `false`.
- `login_wait_seconds`: wait time for login/session steps.
	- Current value: `30`.
- `clustering.random_seed`: clustering seed.
	- Current value: `42`.
- `clustering.write_versioned_output`: write timestamped cluster output in addition to latest.
	- Current value: `true`.
- `clustering.min_cluster_size`: minimum cluster size.
	- Current value: `4`.
- `stopwords`: explicit words removed from JD clustering text analysis.
	- Current value: a large custom list defined in `inputs.json`.

## use

Run NiceGUI Web Server

```bash
python .\main.py
```
