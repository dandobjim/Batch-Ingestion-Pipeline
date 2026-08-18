from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvVarsConfig(BaseSettings):
    api_key: str = Field(alias="GITHUB_API_KEY")
    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_env_vars():
    return EnvVarsConfig()
