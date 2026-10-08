from datetime import datetime
import json
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field, model_validator


class Website(BaseModel):
    address: str
    name: str
    created_at: datetime | None = None


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
    content_hash: Optional[uuid.UUID] = Field(default=None,
                                              description='The generated hash of the content.')

    def generate_content_hash(self) -> JobPost:
        content_json = self.model_dump(exclude={'content-hash'})
        unique_content = json.dumps(content_json, sort_keys=True)
        self.content_hash = uuid.uuid5(uuid.NAMESPACE_DNS, unique_content)

        return self

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


class ParseResult:
    parse_result_chars: int
    saved_jobs: int
    max_retry: int
    exceptions: set[str]

    def set_results(self, parse_result_chars: int, saved_jobs: int, max_retry: int, exceptions: set[str]):
        self.parse_result_chars = parse_result_chars
        self.saved_jobs = saved_jobs
        self.max_retry = max_retry
        self.exceptions = exceptions


class ScrapeRun(BaseModel):
    website_address: str
    start_at: datetime
    end_at: datetime
    crawled_chars: int
    chunks: int
    parse_result_chars: int
    saved_jobs: int
    max_retry: int
    exceptions: list[str]
    skipped_chunks: int
    # Config used
    model: str
    parse_jobs_initial_delay: int
    parse_jobs_interval: int
    parse_jobs_exponential_backoff_factor: int
    parse_jobs_max_retries: int
    openai_timeout: int
    parse_jobs_concurrent_workers: int
    chunk_size: int

    @classmethod
    def from_results(
        cls,
        results: list[ParseResult],
        website_address: str,
        start_at: datetime,
        end_at: datetime,
        crawled_chars: int,
        chunks: int,
        model: str,
        parse_jobs_initial_delay: int,
        parse_jobs_interval: int,
        parse_jobs_exponential_backoff_factor: int,
        parse_jobs_max_retries: int,
        openai_timeout: int,
        parse_jobs_concurrent_workers: int,
        chunk_size: int,
    ) -> ScrapeRun:
        total_chars = sum(r.parse_result_chars for r in results)
        total_jobs = sum(r.saved_jobs for r in results)
        max_r = max((r.max_retry for r in results), default=0)
        skipped_chunks = len([r for r in results if r.saved_jobs == 0])

        exceptions_set = set[str]()
        for r in results:
            exceptions_set.update(r.exceptions)

        return cls(
            parse_result_chars=total_chars,
            saved_jobs=total_jobs,
            max_retry=max_r,
            exceptions=list(exceptions_set),
            website_address=website_address,
            start_at=start_at,
            end_at=end_at,
            crawled_chars=crawled_chars,
            chunks=chunks,
            skipped_chunks=skipped_chunks,
            model=model,
            parse_jobs_initial_delay=parse_jobs_initial_delay,
            parse_jobs_interval=parse_jobs_interval,
            parse_jobs_exponential_backoff_factor=parse_jobs_exponential_backoff_factor,
            parse_jobs_max_retries=parse_jobs_max_retries,
            openai_timeout=openai_timeout,
            parse_jobs_concurrent_workers=parse_jobs_concurrent_workers,
            chunk_size=chunk_size,
        )
