# SmartScraper

SmartScraper is an automated tool designed to crawl websites, extract job
postings using AI, and store the structured data into Supabase. It leverages
**crawl4ai** for efficient web scraping and **Ollama** (via OpenAI-compatible
API) for intelligent data extraction.

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

## ⚙️ Configuration

Create a `.env` file in the `backend/` directory with the following variables:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_or_service_role_key
SUPABASE_WEBSITE_TABLE=websites
SUPABASE_JOB_TABLE=jobs

OLLAMA_MODEL=llama3 # or your preferred model

PARSE_JOBS_INITIAL_DELAY=2
PARSE_JOBS_INTERVAL=1
PARSE_JOBS_EXPONENTIAL_BACKOFF_FACTOR=2
PARSE_JOBS_MAX_RETRIES=3

WEB_SCRAPE_CONCURRENT_WORKERS=5
PARSE_JOBS_CONCURRENT_WORKERS=3
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

| Method | Endpoint    | Description                                  |
| ------ | ----------- | -------------------------------------------- |
| `GET`  | `/health`   | Check if the service is running.             |
| `GET`  | `/websites` | Retrieve the list of websites to be scraped. |
| `POST` | `/websites` | Add a new website to the database.           |
| `POST` | `/scrape`   | Trigger the scraping and AI parsing process. |

## 🔄 How it Works

1. **Target Identification**: The system reads a list of target websites from
   your Supabase `websites` table.
2. **Web Crawling**: `crawl4ai` visits each website, strips away unnecessary
   elements (nav, footer, etc.), and converts the content to clean Markdown.
3. **Chunking**: The markdown content is split into smaller chunks to fit within
   the LLM's context window.
4. **AI Extraction**: Each chunk is sent to Ollama with a specialized prompt
   (`prompt.txt`) to extract job-related data into a JSON format.
5. **Data Persistence**: The structured job objects (title, company, location,
   etc.) are validated and saved into the Supabase `jobs` table.
