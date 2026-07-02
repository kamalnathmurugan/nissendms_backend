"""Application configuration (Phase B).

Reads from environment / `backend/.env`. When the Graph/Azure values are absent
the app runs in **stub mode** (in-memory store, fake OCR) so the UI keeps working
during development. Once the real values are provided it switches to the live
SharePoint Embedded + PostgreSQL backend.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Microsoft Entra / Graph (backend app, app-only) ---
    azure_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_authority: str = "https://login.microsoftonline.com"
    graph_scope: str = "https://graph.microsoft.com/.default"
    graph_base_url: str = "https://graph.microsoft.com/v1.0"

    # --- SharePoint Embedded container ---
    container_type_id: str = ""
    container_id: str = ""  # filled after the container is created
    container_display_name: str = "Vessel DMS Documents"

    # --- Database ---
    database_url: str = ""  # e.g. postgresql+psycopg2://user:pass@host:5432/dms

    # --- Behaviour ---
    month_folder_format: str = "%B %Y"  # e.g. "June 2026"
    ocr_min_confidence: float = 0.5

    @property
    def graph_configured(self) -> bool:
        return bool(
            self.azure_tenant_id
            and self.graph_client_id
            and self.graph_client_secret
            and self.container_type_id
        )

    @property
    def db_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def authority_url(self) -> str:
        return f"{self.graph_authority}/{self.azure_tenant_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
