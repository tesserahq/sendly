from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


# TODO: Once it's clear what's the purpose of this file, move it to the appropriate place
# We already have a settings module, maybe we could use that one instead?
class ServerSettings(BaseSettings):
    url: str = Field(
        default="",
        description="The deployment URL of the server, to be referenced by tools and file services",
    )
    api_prefix: str = Field(
        default="/api",
        description="The prefix for the API endpoints",
    )

    @property
    def file_server_url_prefix(self) -> str:
        return f"{self.url}{self.api_prefix}/files"

    @property
    def api_url(self) -> str:
        return f"{self.url}{self.api_prefix}"

    @field_validator("url")
    def validate_url(cls, v: str) -> str:
        if v.endswith("/"):
            raise ValueError("URL must not end with a '/'")
        return v

    @field_validator("api_prefix")
    def validate_api_prefix(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("API prefix must start with a '/'")
        return v

    def set_url(self, v: str) -> None:
        self.url = v
        self.validate_url(v)  # type: ignore

    def set_api_prefix(self, v: str) -> None:
        self.api_prefix = v
        self.validate_api_prefix(v)  # type: ignore

    class Config:
        env_file_encoding = "utf-8"


server_settings = ServerSettings()
