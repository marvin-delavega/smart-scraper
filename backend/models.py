from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class Website(BaseModel):
    address: str
    name: str
    created_at: datetime | None = None

    def __init__(self, address: str, name: str, created_at: datetime | None = None):
        super().__init__(address=address, name=name, created_at=created_at)

        self.address = address
        self.name = name
        self.created_at = created_at


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
