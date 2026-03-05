"""全局设置（由 .env 加载）"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",   # backend/.env
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = "sk-placeholder"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_name: str = "gpt-4o-mini"

    # 知识库
    docs_dir: Path = Path(__file__).parent.parent.parent / "docs" / "巡检手册"
    chroma_dir: Path = Path(__file__).parent.parent / "chroma_db"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # 告警阈值
    salt_spray_threshold: float = 15.0   # mg/m³
    voc_threshold: float = 1.0            # mg/m³
    temp_max: float = 50.0                # °C
    humidity_max: float = 85.0            # % RH

    # Agent
    max_replan_count: int = 3
    app_port: int = 8000
    log_level: str = "INFO"


settings = Settings()
