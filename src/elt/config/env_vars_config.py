from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class EnvVarsConfig(BaseSettings):
    api_key: str = Field(alias="GITHUB_API_KEY")
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")


@lru_cache
def get_env_vars():
    return EnvVarsConfig()
