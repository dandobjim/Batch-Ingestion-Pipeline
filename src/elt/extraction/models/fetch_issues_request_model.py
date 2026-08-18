from pydantic import BaseModel


class IssuesRequest(BaseModel):
    owner: str
    repo: str
    api_key: str