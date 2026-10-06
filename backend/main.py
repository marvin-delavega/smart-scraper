import asyncio
import itertools
import os

from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, ValidationError, model_validator
from supabase import create_async_client, AsyncClient
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator, PruningContentFilter
from openai import APITimeoutError, AsyncOpenAI

app = FastAPI()

load_dotenv()

url = os.getenv('SUPABASE_URL') or ''
key = os.getenv('SUPABASE_KEY') or ''
website_table = os.getenv('SUPABASE_WEBSITE_TABLE') or ''
job_table = os.getenv('SUPABASE_JOB_TABLE') or ''

ollama_model = os.getenv('OLLAMA_MODEL') or ''

parse_jobs_initial_delay = int(os.getenv('PARSE_JOBS_INITIAL_DELAY') or '0')
parse_jobs_interval = int(os.getenv('PARSE_JOBS_INTERVAL') or '0')
parse_jobs_exponential_backoff_factor = int(os.getenv(
    'PARSE_JOBS_EXPONENTIAL_BACKOFF_FACTOR') or '2')
parse_jobs_max_retries = int(os.getenv('PARSE_JOBS_MAX_RETRIES') or '5')

openai_min_timeout = int(os.getenv('OPENAI_MIN_TIMEOUT') or '30')
openai_max_timeout = int(os.getenv('OPENAI_MAX_TIMEOUT') or '60')

web_scrape_concurrent_workers = int(os.getenv(
    'WEB_SCRAPE_CONCURRENT_WORKERS') or '1')
parse_jobs_concurrent_workers = int(os.getenv(
    'PARSE_JOBS_CONCURRENT_WORKERS') or '1')


print(f'Loaded Supabase URL: {url}')
print(f'Loaded Supabase Key: {key}')
print(f'Loaded Supabase Website Table: {website_table}')
print(f'Loaded Supabase Job Table: {job_table}')
print(f'Loaded Ollama Model: {ollama_model}')
print(f'Loaded Parse Jobs Initial Delay: {parse_jobs_initial_delay}')
print(f'Loaded Parse Jobs Interval: {parse_jobs_interval}')
print(
    f'Loaded Parse Jobs Exponential Factor: {parse_jobs_exponential_backoff_factor}')
print(f'Loaded Parse Jobs Max Retries: {parse_jobs_max_retries}')
print(f'Loaded OpenAI Minimum Timeout: {openai_min_timeout}')
print(f'Loaded OpenAI Maxiumum Timeout: {openai_max_timeout}')
print(f'Loaded Web Scrape Concurrent Workers: {web_scrape_concurrent_workers}')
print(f'Loaded Parse Jobs Concurrent Workers: {parse_jobs_concurrent_workers}')


def get_promt() -> str:
    with open('prompt.txt', 'r', encoding='utf-8') as file:
        return file.read()


base_prompt = get_promt()
print(f'Loaded Base Prompt: {base_prompt}')

ai_client = AsyncOpenAI(
    api_key='ollama', base_url="http://host.docker.internal:11434/v1")
max_retries = int(parse_jobs_max_retries)
scrape_semaphore = asyncio.Semaphore(int(web_scrape_concurrent_workers))
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


class Website(BaseModel):
    address: str
    name: str
    created_at: datetime | None = None

    def __init__(self, address: str, name: str, created_at: datetime | None = None):
        super().__init__(address=address, name=name, created_at=created_at)

        self.address = address
        self.name = name
        self.created_at = created_at


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


@app.post('/scrape')
async def scrape_websites() -> dict[str, Any]:
    websites = [Website(**website) for website in (await get_websites())['data']]

    if not websites:
        return {"message": "No websites found", "data": []}

    scrape_results = await asyncio.gather(*(scrape_website(w) for w in websites))
    print(f'Scraped {len(scrape_results)} websites. Chunking...')

    chunks = list(itertools.chain.from_iterable([await split_markdown(m, 3000) for m in scrape_results]))
    print(f'Scrape results chunked into {len(chunks)} chunks. Parsing...')

    parse_results = await asyncio.gather(*(parse_and_save_jobs(c) for c in chunks))
    total_jobs = sum(parse_results)
    print(f'Saved {total_jobs} jobs in total. See dashboard')

    return {"message": "Scraping completed", "data": total_jobs}


async def scrape_website(website: Website) -> tuple[Website, str]:
    async with scrape_semaphore:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=website.address, config=crawler_config)
            return (website, result.markdown.raw_markdown)


class JobPost(BaseModel):
    title: str = Field(description='The exact job title')
    desc: Optional[str] = Field(default=None,
                                description='The summary of the job description')
    company: Optional[str] = Field(default=None,
                                   description='The name, website, or person of the job poster')
    salary_range: Optional[str] = Field(default=None,
                                        description='The salary range, this could be range or just a single value')
    location: Optional[str] = Field(default=None,
                                    description='The location of the work, could be a place or remote')
    links: Optional[list[str]] = Field(default=[],
                                       description='The links related to the job posting')
    website_address: Optional[str] = Field(default=None,
                                           description='The website address of the job posting.')
    primary_link: str = Field(
        description='The primary link of the job posting')

    def set_website_address(self, website: Website):
        self.website_address = website.address


class JobList(BaseModel):
    jobs: list[JobPost]

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"jobs": data}

        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    return {"jobs": value}

        return data

    def assign_website(self, website: Website):
        [job.set_website_address(website) for job in self.jobs]


async def split_markdown(markdown: tuple[Website, str], max_size: int) -> list[tuple[Website, str]]:
    return [(markdown[0], markdown[1][i: i + max_size]) for i in range(0, len(markdown[1]), max_size)]


async def save_jobs(list: JobList, supabase: AsyncClient) -> int:
    job_json_list = [job.model_dump() for job in list.jobs]
    result = await supabase.table(job_table).upsert(job_json_list).execute()

    return len(result.data) or 0


async def parse_and_save_jobs(chunk: tuple[Website, str]) -> int:
    count = 0
    async with parse_jobs_semaphore:
        supabase = await create_supabase()
        delay = parse_jobs_initial_delay
        next_attempt_reinforcement = 'None'
        timeout = openai_min_timeout

        for attempt in range(1, max_retries + 1):
            print(f'Parsing attempt #{attempt}.')
            try:
                response = await ai_client.chat.completions.create(
                    model=ollama_model,
                    messages=[
                        {
                            "role": "system",
                            "content": base_prompt
                        },
                        {
                            "role": "user",
                            "content": f"website_address: {chunk[0]}  \nThis is attempt #{attempt}, last attempt error:  \n{next_attempt_reinforcement}  \nMARKDOWN:  \n{chunk[1]}"
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    timeout=timeout
                )

                if not response.choices or response.choices[0].message.content is None:
                    return count

                raw_content = response.choices[0].message.content

                jobs = JobList.model_validate_json(raw_content)
                jobs.assign_website(chunk[0])

                saved_count = await save_jobs(jobs, supabase)

                print(f'Parsed and saved {saved_count} jobs')

                count += saved_count
                timeout = openai_min_timeout

                await asyncio.sleep(parse_jobs_interval)
                break
            except APITimeoutError as e:  # openai timeout error
                print_error(e, e.message)

                if not has_retries(attempt):
                    break

                next_attempt_reinforcement = f'Timeout. Try to keep the session within {openai_min_timeout} to {openai_max_timeout} seconds.'
                timeout = openai_max_timeout
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
