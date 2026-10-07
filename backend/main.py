import asyncio
import os

from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import create_async_client, AsyncClient
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator, PruningContentFilter
from openai import APITimeoutError, AsyncOpenAI

from models import Website, JobList


app = FastAPI()

load_dotenv()

url = os.getenv('SUPABASE_URL') or ''
key = os.getenv('SUPABASE_KEY') or ''
website_table = os.getenv('SUPABASE_WEBSITE_TABLE') or ''
job_table = os.getenv('SUPABASE_JOB_TABLE') or ''
scrape_run_table = os.getenv('SUPABASE_SCRAPE_RUN_TABLE') or ''

ollama_model = os.getenv('OLLAMA_MODEL') or ''

parse_jobs_initial_delay = int(os.getenv('PARSE_JOBS_INITIAL_DELAY') or '0')
parse_jobs_interval = int(os.getenv('PARSE_JOBS_INTERVAL') or '0')
parse_jobs_exponential_backoff_factor = int(os.getenv(
    'PARSE_JOBS_EXPONENTIAL_BACKOFF_FACTOR') or '2')
parse_jobs_max_retries = int(os.getenv('PARSE_JOBS_MAX_RETRIES') or '5')

openai_timeout = int(os.getenv('OPENAI_TIMEOUT') or '120')

chunk_size = int(os.getenv('CHUNK_SIZE') or '3000')

parse_jobs_concurrent_workers = int(os.getenv(
    'PARSE_JOBS_CONCURRENT_WORKERS') or '1')


print(f'Loaded Supabase URL: {url}')
print(f'Loaded Supabase Key: {key}')
print(f'Loaded Supabase Website Table: {website_table}')
print(f'Loaded Supabase Job Table: {job_table}')
print(f'Loaded Supabase Scrape Run Table: {scrape_run_table}')
print(f'Loaded Ollama Model: {ollama_model}')
print(f'Loaded Parse Jobs Initial Delay: {parse_jobs_initial_delay}')
print(f'Loaded Parse Jobs Interval: {parse_jobs_interval}')
print(
    f'Loaded Parse Jobs Exponential Factor: {parse_jobs_exponential_backoff_factor}')
print(f'Loaded Parse Jobs Max Retries: {parse_jobs_max_retries}')
print(f'Loaded OpenAI Timeout: {openai_timeout}')
print(f'Loaded Chunk Size: {chunk_size}')
print(f'Loaded Parse Jobs Concurrent Workers: {parse_jobs_concurrent_workers}')


def get_promt() -> str:
    with open('prompt.txt', 'r', encoding='utf-8') as file:
        return file.read()


base_prompt = get_promt()
print(f'Loaded Base Prompt: {base_prompt}')

ai_client = AsyncOpenAI(
    api_key='ollama', base_url="http://host.docker.internal:11434/v1")
max_retries = int(parse_jobs_max_retries)
parse_jobs_semaphore = asyncio.Semaphore(int(parse_jobs_concurrent_workers))

prune_filter = PruningContentFilter(
    threshold=0.4, threshold_type='fixed', min_word_threshold=20)
crawler_config = CrawlerRunConfig(
    markdown_generator=DefaultMarkdownGenerator(content_filter=prune_filter),
    exclude_all_images=True,
    excluded_tags=['nav', 'footer', 'aside', 'header', 'script', 'style'])


async def create_supabase() -> AsyncClient:
    return await create_async_client(url, key)


@app.get('/health')
def health_check():
    return {"status": "OK"}


@app.get('/websites')
async def get_websites() -> dict[str, Any]:
    supabase = await create_supabase()
    try:
        result = await supabase.table(website_table).select('*').execute()
        return {
            "message": "Websites retrieved successfully",
            "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/websites')
async def add_website(website: Website) -> dict[str, Any]:
    supabase = await create_supabase()
    try:
        result = await supabase.table(website_table).insert(website.model_dump(exclude_none=True)).select('*').execute()

        if not result.data:
            return {"message": "No website was added", "code": 502, "data": result.data}

        return {"message": "Website added successfully", "code": 201, "data": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/scraper/run')
async def trigger_scraper(tasks: BackgroundTasks) -> dict[str, Any]:
    tasks.add_task(run_scraper)
    return {'message': 'Scraper started', 'data': ''}


async def run_scraper():
    print(f'Starting scraper...')

    websites = [Website(**website) for website in (await get_websites())['data']]
    print(f'Found {len(websites)} websites to scrape')

    total_jobs_processed = 0
    for w in websites:
        total_jobs_processed += await scrape(w)

    print(
        f'Scraped {total_jobs_processed} jobs from {len(websites)} websites. See dashboard')


async def scrape(website: Website) -> int:
    print(f'Scraping {website.name}: {website.address}...')

    crawl_result = await crawl(website)
    print(f'Crawl result: {len(crawl_result)} characters. Chunking...')

    chunks = get_chunks(crawl_result, chunk_size)
    print(
        f'Chunk result: {len(chunks)} chunks. Calling {ollama_model} to parse...')

    parse_results = await asyncio.gather(*(parse_and_save_jobs(website, c) for c in chunks))
    jobs_processed = sum(parse_results)

    print(f'Parsed and saved {jobs_processed} jobs from {website.name}')
    return jobs_processed


async def crawl(website: Website) -> str:
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=website.address, config=crawler_config)
        return result.markdown.raw_markdown


def get_chunks(markdown: str, max_size: int) -> list[str]:
    return [markdown[i: i + max_size] for i in range(0, len(markdown), max_size)]


async def save_jobs(list: JobList, supabase: AsyncClient) -> int:
    job_json_list = [job.model_dump() for job in list.jobs]
    result = await supabase.table(job_table).upsert(job_json_list).execute()

    return len(result.data) or 0


async def parse_and_save_jobs(website: Website, chunk: str) -> int:
    count = 0
    async with parse_jobs_semaphore:
        supabase = await create_supabase()
        delay = parse_jobs_initial_delay
        next_attempt_reinforcement = 'None'

        for attempt in range(1, max_retries + 1):
            print(
                f'Attempt #{attempt}. Calling {ollama_model} to parse {len(chunk)} characters... ')
            try:
                start_time = datetime.now()
                response = await ai_client.chat.completions.create(
                    model=ollama_model,
                    messages=[
                        {
                            "role": "system",
                            "content": base_prompt
                        },
                        {
                            "role": "user",
                            "content": f"website_address: {chunk}  \nThis is attempt #{attempt}, last attempt error:  \n{next_attempt_reinforcement}  \nMARKDOWN:  \n{chunk[1]}"
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    timeout=openai_timeout
                )
                elapsed_time_parsing = datetime.now() - start_time

                if not response.choices or response.choices[0].message.content is None:
                    return count

                raw_content = response.choices[0].message.content
                print(
                    f'{ollama_model} completed parsing in {elapsed_time_parsing.seconds} seconds, at attempt #{attempt}. Serializing...')

                joblist = JobList.model_validate_json(raw_content)

                if not joblist.jobs:
                    print(
                        f'Could not serialize {ollama_model} reponse. Skipping...')

                joblist.assign_website(website)

                print(
                    f'Serialized {len(joblist.jobs)} jobs. Saving to {job_table} table...')

                saved_count = await save_jobs(joblist, supabase)

                print(f'Success! Parsed and saved {saved_count} jobs.')

                count += saved_count

                await asyncio.sleep(parse_jobs_interval)
                break
            except APITimeoutError as e:  # openai timeout error
                print_error(e, e.message)

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = f'Timeout. Try to keep the session within {openai_timeout} seconds.'
                delay = await exponential_backoff(delay)
            except APIError as e:  # supabase api error
                print_error(e, e.message or '')

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = 'None'
                delay = await exponential_backoff(delay)
            except ValidationError as e:
                print_error(e, e.json())

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = 'Pydantic validation error. Optimistic Retry. Try to fill up all fields.'
                delay = await exponential_backoff(delay)
            except Exception as e:
                print_error(e, str(e))

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = 'None'
                delay = await exponential_backoff(delay)

    return count


def has_retries(attempt: int) -> bool:
    has_retries = attempt < max_retries

    if not has_retries:
        print(f'Max retries reached. Skipping...')

    return has_retries


def print_error(e: Exception, msg: str):
    print(f'{e.__class__}: {msg}. Retrying...')


async def exponential_backoff(current_delay: int) -> int:
    await asyncio.sleep(current_delay)
    return current_delay * parse_jobs_exponential_backoff_factor
