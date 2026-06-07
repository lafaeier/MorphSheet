import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self.deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
        self.sandbox_timeout: int = int(os.getenv("SANDBOX_TIMEOUT", "30"))
        self.max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
        self.data_dir: str = os.getenv("DATA_DIR", "data")
        self.chroma_db_dir: str = os.getenv("CHROMA_DB_DIR", "chroma_db")
        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PORT", "8765"))


settings = Settings()
