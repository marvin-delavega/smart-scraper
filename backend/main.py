import asyncio
from contextlib import asynccontextmanager
import os

from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import create_async_client, AsyncClient
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator, PruningContentFilter
from openai import APITimeoutError, AsyncOpenAI

from models import ParseResult, ScrapeRun, Website, JobList


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.supabase = await create_async_client(url, key)
    yield


def get_supabase(request: Request) -> AsyncClient:
    return request.app.state.supabase


app = FastAPI(lifespan=lifespan)

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

is_test_mode_single_run = (os.getenv('TEST_MODE_SINGLE_RUN') or '0') == '1'


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


@app.get('/health')
def health_check():
    return {"status": "OK"}


@app.get('/websites')
async def get_websites(supabase: AsyncClient = Depends(get_supabase)) -> dict[str, Any]:
    try:
        result = await supabase.table(website_table).select('*').execute()
        return {
            "message": "Websites retrieved successfully",
            "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/websites')
async def add_website(website: Website, supabase: AsyncClient = Depends(get_supabase)) -> dict[str, Any]:
    try:
        result = await supabase.table(website_table).insert(website.model_dump(exclude_none=True)).select('*').execute()

        if not result.data:
            return {"message": "No website was added", "code": 502, "data": result.data}

        return {"message": "Website added successfully", "code": 201, "data": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/scraper/run')
async def trigger_scraper(tasks: BackgroundTasks, supabase: AsyncClient = Depends(get_supabase)) -> dict[str, Any]:
    tasks.add_task(run_scraper, supabase)
    return {'message': 'Scraper started', 'data': ''}


async def run_scraper(supabase: AsyncClient):
    print(f'Starting scraper...')

    websites: list[Website]

    if is_test_mode_single_run:
        websites = [await get_one_website(supabase)]
    else:
        websites = [Website(**data) for data in (await get_websites(supabase))['data']]

    print(f'Found {len(websites)} websites to scrape')

    runs: list[ScrapeRun] = []
    for w in websites:
        runs.append(await scrape(w, supabase))

    await save_runs(runs, supabase)

    print(
        f'Scraped {sum(r.saved_jobs for r in runs)} jobs from {len(websites)} websites. See dashboard')


async def get_one_website(supabase: AsyncClient) -> Website:
    result = await supabase.table(website_table).select('*').limit(1).single().execute()
    return Website.model_validate(result.data)


async def scrape(website: Website, supabase: AsyncClient) -> ScrapeRun:
    start_at = datetime.now()
    print(f'Scraping {website.name}: {website.address}...')

    crawl_result = await crawl(website)
    crawled_chars = len(crawl_result)
    print(f'Crawl result: {crawled_chars} characters. Chunking...')

    chunks = get_chunks(crawl_result, chunk_size)
    chunk_count = len(chunks)
    print(
        f'Chunk result: {chunk_count} chunks. Calling {ollama_model} to parse...')

    parse_results = await asyncio.gather(*(parse_and_save_jobs(website, c, supabase) for c in chunks))
    end_at = datetime.now()
    run = ScrapeRun.from_results(
        parse_results,
        website.address,
        start_at,
        end_at,
        crawled_chars,
        chunk_count,
        ollama_model,
        parse_jobs_initial_delay,
        parse_jobs_interval,
        parse_jobs_exponential_backoff_factor,
        parse_jobs_max_retries,
        openai_timeout,
        parse_jobs_concurrent_workers,
        chunk_size)

    print(f'Parsed and saved {run.saved_jobs} jobs from {website.name}')
    return run


async def crawl(website: Website) -> str:
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=website.address, config=crawler_config)
        return result.markdown.raw_markdown


def get_chunks(markdown: str, max_size: int) -> list[str]:
    return [markdown[i: i + max_size] for i in range(0, len(markdown), max_size)]


async def save_jobs(list: JobList, supabase: AsyncClient) -> int:
    job_json_list = [job.generate_content_hash().model_dump(mode='json')
                     for job in list.jobs]
    result = await supabase.table(job_table).upsert(job_json_list).execute()

    return len(result.data) or 0


async def save_runs(runs: list[ScrapeRun], supabase: AsyncClient):
    run_json_list = [run.model_dump(mode='json') for run in runs]
    await supabase.table(scrape_run_table).insert(run_json_list).execute()


async def parse_and_save_jobs(website: Website, chunk: str, supabase: AsyncClient) -> ParseResult:
    async with parse_jobs_semaphore:
        result = ParseResult()
        delay = parse_jobs_initial_delay
        next_attempt_reinforcement = 'None'
        exceptions = set[str]()

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
                    break

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
                print(f'Success! Parsed and saved {saved_count} jobs')

                result.set_results(
                    len(raw_content), saved_count, attempt, exceptions)

                await asyncio.sleep(parse_jobs_interval)
                break
            except APITimeoutError as e:  # openai timeout error
                exceptions.update(e.message)
                print_error(e, e.message)

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = f'Timeout. Try to keep the session within {openai_timeout} seconds.'
                delay = await exponential_backoff(delay)
            except APIError as e:  # supabase api error
                exceptions.update(e.message or '')
                print_error(e, e.message or '')

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = f'Supabase error: {e.message}. Try to follow database constraints.'
                delay = await exponential_backoff(delay)
            except ValidationError as e:
                exceptions.update(e.json())
                print_error(e, e.json())

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = 'Pydantic validation error. Optimistic Retry. Try to fill up all fields correctly.'
                delay = await exponential_backoff(delay)
            except Exception as e:
                exceptions.update(str(e))
                print_error(e, str(e))

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = 'None'
                delay = await exponential_backoff(delay)

        return result


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
