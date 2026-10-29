"""All configuration comes from environment variables (12-factor); nothing secret lives in code."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", "postgresql://flood:flood@localhost:5432/flood"))
    # "nominatim" in production; "fixture" in tests (reads a JSON file, no network)
    geocoder: str = field(default_factory=lambda: os.environ.get("GEOCODER", "nominatim"))
    geocoder_fixture: str = field(default_factory=lambda: os.environ.get("GEOCODER_FIXTURE", ""))
    nominatim_url: str = field(default_factory=lambda: os.environ.get(
        "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"))
    # Nominatim's usage policy asks for an identifying User-Agent with contact details.
    contact_email: str = field(default_factory=lambda: os.environ.get("CONTACT_EMAIL", ""))
    # Nominatim allows at most 1 request per second, so batches are capped.
    max_batch_rows: int = field(default_factory=lambda: int(os.environ.get("MAX_BATCH_ROWS", "100")))
    max_upload_bytes: int = 1_000_000
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


settings = Settings()
