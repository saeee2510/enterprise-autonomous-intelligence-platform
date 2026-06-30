import os
from dataclasses import dataclass


@dataclass
class Config:
    """
    Central configuration for EAIP system
    """

    # =========================
    # DATABASE CONFIG
    # =========================
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5450))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "eaip")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")

    # Connection string (computed)
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )

    # =========================
    # LLM CONFIG
    # =========================
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", 0.1))

    # =========================
    # EMBEDDING CONFIG
    # =========================
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "text-embedding-3-small"
    )
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", 1536))

    # =========================
    # RETRIEVAL CONFIG
    # =========================
    TOP_K_RETRIEVAL: int = int(os.getenv("TOP_K_RETRIEVAL", 5))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", 0.75))

    # =========================
    # SYSTEM CONFIG
    # =========================
    APP_NAME: str = "Enterprise Autonomous Intelligence Platform"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"


# Singleton config instance
config = Config()