import os


class Config:
    # Postgres in production (set DATABASE_URL in Render); SQLite locally.
    # Render gives postgres:// URLs, SQLAlchemy needs postgresql://
    _db_url = os.environ.get("DATABASE_URL", "sqlite:///sensors.db")
    SQLALCHEMY_DATABASE_URI = _db_url.replace("postgres://", "postgresql://", 1)

    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get("CACHE_TIMEOUT", 30))

    SEED_READINGS = int(os.environ.get("SEED_READINGS", 20000))
    MAX_PAGE_SIZE = 1000
    DEFAULT_PAGE_SIZE = 100


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    CACHE_TYPE = "NullCache"
    SEED_READINGS = 500
