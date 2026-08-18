from pydantic import BaseModel, Field


class IssuesRequest(BaseModel):
    owner: str
    repo: str
    api_key: str
    per_page: int = Field(default=100, ge=1, le=100)
