import sys
import os

# Add backend/ to sys.path so all backend modules are importable from tests/
# (pytest.ini_options pythonpath also handles this; kept as fallback)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def sample_sources():
    """Typical source attribution entries returned by CourseSearchTool."""
    return [
        {"label": "Python 101 - Lesson 1", "url": "https://example.com/python/1"},
        {"label": "Python 101 - Lesson 2", "url": "https://example.com/python/2"},
    ]


@pytest.fixture
def sample_analytics():
    """Typical get_course_analytics() return value."""
    return {
        "total_courses": 2,
        "course_titles": ["Python 101", "Machine Learning Basics"],
    }


@pytest.fixture
def mock_rag_system():
    """
    Fully configured MagicMock of RAGSystem.

    Provides sensible defaults so tests only need to override the behaviour
    they care about. Shared across test files via conftest.py.
    """
    rag = MagicMock()
    rag.query.return_value = ("Sample answer.", [])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Python 101", "Machine Learning Basics"],
    }
    rag.session_manager.create_session.return_value = "new-session-id"
    return rag
