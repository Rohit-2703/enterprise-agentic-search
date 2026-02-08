"""Configuration management using pydantic-settings."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"
    
    # Pinecone Configuration
    pinecone_api_key: str
    pinecone_environment: str = "us-east-1-aws"
    pinecone_index_name: str = "enterprise-search"
    pinecone_dimension: int = 3072
    
    # LangSmith Configuration
    langchain_tracing_v2: bool = True
    langchain_api_key: Optional[str] = None
    langchain_project: str = "enterprise-search"
    langchain_endpoint: str = "https://api.smith.langchain.com"
    
    # PostgreSQL Configuration
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "enterprise_search"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: Optional[str] = None
    
    # Redis Configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_url: Optional[str] = None
    
    # Application Configuration
    default_username: str = "admin"
    default_password: str = "admin123"
    log_level: str = "INFO"
    environment: str = "development"
    
    # Cache Configuration
    redis_cache_ttl: int = 3600  # 1 hour
    postgres_cache_ttl: int = 604800  # 7 days
    enable_caching: bool = True
    
    # Agent Configuration
    confidence_threshold: float = 0.7
    max_retries: int = 2
    enable_self_healing: bool = True
    enable_query_decomposition: bool = True
    min_similarity_score: float = 0.6  # Minimum similarity score for retrieval (lower = more results)
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # GitHub Configuration
    github_api_token: Optional[str] = None
    github_organization: Optional[str] = None  # Filter searches to specific organization
    
    # JIRA Configuration
    jira_url: Optional[str] = None
    jira_email: Optional[str] = None
    jira_api_token: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from environment variables
    
    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def redis_connection_url(self) -> str:
        """Get Redis connection URL."""
        if self.redis_url:
            return self.redis_url
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
