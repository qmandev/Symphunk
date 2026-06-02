from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Splunk REST (port 8089) — standard token
    splunk_host: str = "localhost"
    splunk_port: int = 8089
    splunk_token: str = Field(default="", description="Standard REST token (symphunk-rest)")
    splunk_password: str = "changeme123!"

    # MCP Server — encrypted token (MCP-only, will 401 against REST 8089)
    mcp_url: str = "http://localhost:8000/en-US/splunkd/__raw/services/mcp"
    mcp_token: str = Field(default="", description="Encrypted MCP token")

    # HEC (port 8088)
    hec_url: str = "https://localhost:8088"
    hec_token: str = Field(default="", description="HEC token (symphunk-hec)")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = "claude-sonnet-4-6"

    # Orchestrator
    max_concurrent_agents: int = 3
    poll_interval_seconds: int = 30
    max_searches_per_run: int = 10


settings = Settings()
