import asyncio
import itertools
import os

from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, ValidationError
from supabase import create_async_client, AsyncClient
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, DefaultMarkdownGenerator, PruningContentFilter
from openai import AsyncOpenAI

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

    total_jobs = await asyncio.gather(*(parse_and_save_jobs(c) for c in chunks))
    print(f'Scraped {total_jobs} jobs in total. See dashboard')

    return {"message": "Scraping completed", "data": 0}


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

        for attempt in range(1, max_retries + 1):
            last_attempt_error = 'None'
            try:
                response = await ai_client.chat.completions.create(
                    model=ollama_model,
                    messages=[
                        {
                            "role": "system",
                            "content": f"This is attempt #{attempt}, last attempt error:  \n{last_attempt_error}  \n{base_prompt}"},
                        {
                            "role": "user",
                            "content": chunk[1]
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1
                )

                if not response.choices or response.choices[0].message.content is None:
                    return count

                raw_content = response.choices[0].message.content

                jobs = JobList.model_validate_json(raw_content)
                jobs.assign_website(chunk[0])

                saved_count = await save_jobs(jobs, supabase)

                print(f'Parsed and saved {saved_count} jobs')

                count += saved_count

                await asyncio.sleep(parse_jobs_interval)
                attempt = 0
            except APIError as e:
                error = str(e)
                if e.code == '23505':  # Duplicate key
                    print(f'{e.__class__}: {error}. Retrying...')
                else:
                    HTTPException(status_code=500,
                                  detail=f'{e.__class__}: {error}')

                last_attempt_error = 'Duplicate key: primary_link. Try to pick a different key.'
                await asyncio.sleep(delay)
                delay *= parse_jobs_exponential_backoff_factor
            except ValidationError as e:
                error = str(e)

                if attempt >= max_retries:
                    raise HTTPException(
                        status_code=503, detail=f'Validation failed, max retries reached. {e.__class__}: ' + error)

                print(f'{e.__class__}: {error}. Retrying...')

                last_attempt_error = 'Pydantic validation error. Optimistic Retry. Try to fill up all all fields.'
                await asyncio.sleep(delay)
                delay *= parse_jobs_exponential_backoff_factor
            except Exception as e:
                error = str(e)

                if attempt >= max_retries:
                    raise HTTPException(
                        status_code=503, detail=f'Model unavailable, max retries reached. {e.__class__}: ' + error)

                if '400' in error or '404' in error or '500' in error:
                    print(f'{e.__class__}: {error}. Retrying...')
                else:
                    raise HTTPException(
                        status_code=500, detail=f'{e.__class__}: {error}')

                last_attempt_error = error
                await asyncio.sleep(delay)
                delay *= parse_jobs_exponential_backoff_factor

    return count
