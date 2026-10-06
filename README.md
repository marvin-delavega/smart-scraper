# SmartScraper | An AI Job Hunter on Ollama

SmartScraper is an automated tool designed to crawl websites, extract job
postings using AI, and store the structured data into Supabase. It leverages
**crawl4ai** for efficient web scraping and **Ollama** (via OpenAI-compatible
API) for intelligent data extraction.

## ⭐ Goal

My goal was to integrate AI into an interesting project. I was job hunting at
the time (october 5, 2026), so I had the idea of web scraping job posts. The
problem is that these websites could change by the time I've done configuring
bespoke scraping logic. This is the part I could leverage AI, I thought of
injecting an instruction and the raw scraped data and have it create
json-formatted results for me. This way, I would not rely on specific scraping
logic per website and this would allow me to add as many websites to scrape as
possible.

## 🚀 Features

- **Automated Web Scraping**: Uses `crawl4ai` with headless Chromium to fetch
  content from target websites.
- **AI-Powered Parsing**: Utilizes LLMs (via Ollama) to accurately extract job
  details like titles, descriptions, salaries, and locations from raw markdown.
- **Structured Storage**: Automatically saves extracted job listings into a
  Supabase database.
- **Concurrency & Resilience**: Supports concurrent scraping and parsing with
  built-in exponential backoff and retry logic.
- **Dockerized Environment**: Easy to deploy and run using Docker and Docker
  Compose.

## 🛠️ Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Scraping**: [crawl4ai](https://github.com/unclecode/crawl4ai)
- **AI Integration**: [OpenAI SDK](https://github.com/openai/openai-python)
  (connecting to Ollama)
- **Database**: [Supabase](https://supabase.com/)
- **Containerization**: Docker & Docker Compose

## 📋 Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose.
- [Ollama](https://ollama.ai/) running locally (or accessible via network).
- A [Supabase](https://supabase.com/) project with two tables:
  - `websites`: To store the URLs and names of sites to scrape.
  - `jobs`: To store the extracted job postings.

## ⚙️ Environment Variables

The following environment variables can be set in `.env` file (`backend/.env`):

| Variable                                | Default       | Description                                      |
| --------------------------------------- | ------------- | ------------------------------------------------ |
| `SUPABASE_URL`                          | -             | Your Supabase project URL                        |
| `SUPABASE_KEY`                          | -             | Your Supabase anon/service role key              |
| `SUPABASE_WEBSITE_TABLE`                | `websites`    | Name of the websites table                       |
| `SUPABASE_JOB_TABLE`                    | `jobs`        | Name of the jobs table                           |
| `OLLAMA_MODEL`                          | `llama3.2:3b` | The Ollama model to use for parsing              |
| `OPENAI_TIMEOUT`                        | `120`         | Timeout in seconds for OpenAI API calls          |
| `CHUNK_SIZE`                            | `3000`        | Size of markdown chunks for AI parsing           |
| `PARSE_JOBS_INITIAL_DELAY`              | `2`           | Initial delay (seconds) between parsing attempts |
| `PARSE_JOBS_INTERVAL`                   | `1`           | Interval (seconds) between retry attempts        |
| `PARSE_JOBS_EXPONENTIAL_BACKOFF_FACTOR` | `2`           | Factor for exponential backoff                   |
| `PARSE_JOBS_MAX_RETRIES`                | `5`           | Maximum number of retry attempts                 |
| `PARSE_JOBS_CONCURRENT_WORKERS`         | `1`           | Concurrent workers for job parsing               |

### Create ENV File

Create a `.env` file in the `backend/` directory with the following variables:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
SUPABASE_WEBSITE_TABLE=website
SUPABASE_JOB_TABLE=job

OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2:3b # or any model you want

PARSE_JOBS_INITIAL_DELAY=0
PARSE_JOBS_INTERVAL=0
PARSE_JOBS_EXPONENTIAL_BACKOFF_FACTOR=1
PARSE_JOBS_MAX_RETRIES=10

OPENAI_TIMEOUT=120

PARSE_JOBS_CONCURRENT_WORKERS=1

CHUNK_SIZE=3000
```

## 🚀 Getting Started

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/SmartScraper.git
   cd SmartScraper
   ```

2. **Run with Docker Compose:**
   ```bash
   cd backend
   docker compose up --build
   ```

3. **Access the API:**
   - The API will be available at `http://localhost:8000`.
   - Interactive API docs (Swagger UI) at `http://localhost:8000/docs`.

## 📡 API Endpoints

| Method | Endpoint       | Description                                                       |
| ------ | -------------- | ----------------------------------------------------------------- |
| `GET`  | `/health`      | Check if the service is running.                                  |
| `GET`  | `/websites`    | Retrieve the list of websites to be scraped.                      |
| `POST` | `/websites`    | Add a new website to the database.                                |
| `POST` | `/scraper/run` | Trigger the scraping and AI parsing process (runs in background). |

## 🔄 How it Works

1. **Target Identification**: The system reads a list of target websites from
   your Supabase `websites` table.
2. **Web Crawling**: `crawl4ai` visits each website, strips away unnecessary
   elements (nav, footer, etc.), and converts the content to clean Markdown.
3. **Chunking**: The markdown content is split into smaller chunks (default size
   configurable via `CHUNK_SIZE` env var, default 3000) to fit within the LLM's
   context window.
4. **AI Extraction**: Each chunk is sent to Ollama with a specialized prompt
   (`prompt.txt`) to extract job-related data into a JSON format. The system
   supports retry logic with exponential backoff, prompt reinforcement based on
   last attempt errors, and handles the following error types:
   - **API Timeout**: Retries with increasing delays up to
     `PARSE_JOBS_MAX_RETRIES`
   - **Supabase API Errors**: Retries with exponential backoff
   - **Pydantic Validation Errors**: Optimistic retries to fill missing fields
5. **Data Persistence**: The structured job objects (title, company, location,
   etc.) are validated and saved into the Supabase `jobs` table using upsert
   operation (supports idempotent updates).
