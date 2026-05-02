"""Service locator for the process-wide :class:`~engine.repository.base.BaseRunRepository`."""

from __future__ import annotations

from functools import lru_cache

from engine.db_config import create_db_and_tables, get_engine
from engine.repository.adapters import SQLModelRunRepository
from engine.repository.base import BaseRunRepository


@lru_cache(maxsize=1)
def get_repository() -> BaseRunRepository:
    """Return the cached repository for the active :func:`~engine.db_config.resolve_database_url`."""
    create_db_and_tables()
    return SQLModelRunRepository(engine=get_engine())


def reset_repository_cache() -> None:
    """Clear the cached repository. Use in tests after changing database configuration."""
    get_repository.cache_clear()
