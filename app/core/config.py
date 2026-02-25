"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with defaults and env var overrides."""

    # Database
    database_url: str = (
        "postgresql://fleximarket:fleximarket@localhost:5432/fleximarket_db"
    )
    test_database_url: str = (
        "postgresql://fleximarket:fleximarket@localhost:5433/fleximarket_test_db"
    )

    # App
    app_env: str = "development"
    app_port: int = 8000

    # Reconciliation thresholds
    settlement_delay_threshold_days: int = 5
    fee_tolerance_percent: float = 0.5
    amount_tolerance_percent: float = 0.01
    fx_rate_tolerance_percent: float = 2.0

    # Processor fee configuration (expected fee percentages)
    payflow_fee_percent: float = 2.5
    transactmax_fee_percent: float = 3.2
    globalpay_fee_percent: float = 2.8

    # Severity thresholds (USD)
    severity_critical_threshold: float = 1000.0
    severity_high_threshold: float = 100.0
    severity_medium_threshold: float = 10.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
