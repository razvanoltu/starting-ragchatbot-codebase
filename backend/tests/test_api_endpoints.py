"""
Tests for FastAPI API endpoints (/api/query, /api/courses, /api/session/{id}).

A minimal test app is defined inline to mirror app.py's endpoints with an
injected mock RAGSystem, avoiding the static file mounting and heavy
dependency initialisation that make importing app.py directly impractical
in a test environment.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import List, Optional
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Pydantic models — mirrors app.py exactly
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    session_id: str


class CourseStats(BaseModel):
    total_courses: int
    course_titles: List[str]


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def create_test_app(rag_system) -> FastAPI:
    """
    Minimal FastAPI app that mirrors the API surface of app.py.

    The RAGSystem is injected rather than instantiated at module level so
    each test can configure its own mock without cross-test interference.
    No static files are mounted, which is the main source of import pain
    when trying to reuse the production app directly.
    """
    app = FastAPI()

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = rag_system.session_manager.create_session()
            answer, sources = rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/session/{session_id}")
    async def delete_session(session_id: str):
        rag_system.session_manager.delete_session(session_id)
        return {"status": "ok"}

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag():
    """RAGSystem mock with sensible defaults for endpoint tests."""
    rag = MagicMock()
    rag.query.return_value = ("Sample answer.", [])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Python 101", "Machine Learning Basics"],
    }
    rag.session_manager.create_session.return_value = "new-session-id"
    return rag


@pytest.fixture
def client(mock_rag):
    """TestClient backed by the minimal test app."""
    return TestClient(create_test_app(mock_rag))


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

class TestQueryEndpoint:

    def test_returns_200_with_answer_and_session_id(self, client, mock_rag):
        """Happy path: returns answer, sources, and the provided session_id."""
        mock_rag.query.return_value = ("Python is a programming language.", [])

        response = client.post(
            "/api/query",
            json={"query": "What is Python?", "session_id": "existing-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Python is a programming language."
        assert data["session_id"] == "existing-session"
        assert isinstance(data["sources"], list)

    def test_creates_session_when_none_provided(self, client, mock_rag):
        """When session_id is absent, a new session is created and returned."""
        mock_rag.query.return_value = ("An answer.", [])

        response = client.post("/api/query", json={"query": "Hello"})

        assert response.status_code == 200
        mock_rag.session_manager.create_session.assert_called_once()
        assert response.json()["session_id"] == "new-session-id"

    def test_uses_provided_session_id_without_creating_new(self, client, mock_rag):
        """When session_id is given, create_session must NOT be called."""
        mock_rag.query.return_value = ("Response.", [])

        client.post(
            "/api/query",
            json={"query": "Follow-up", "session_id": "my-session"},
        )

        mock_rag.session_manager.create_session.assert_not_called()

    def test_null_session_id_triggers_session_creation(self, client, mock_rag):
        """Explicitly passing session_id=null is treated the same as omitting it."""
        mock_rag.query.return_value = ("ok", [])

        response = client.post(
            "/api/query", json={"query": "Hello", "session_id": None}
        )

        mock_rag.session_manager.create_session.assert_called_once()
        assert response.status_code == 200

    def test_includes_sources_in_response(self, client, mock_rag):
        """Sources returned by rag_system.query() appear in the API response."""
        sources = [{"label": "Python 101 - Lesson 1", "url": "https://example.com/1"}]
        mock_rag.query.return_value = ("Answer with sources.", sources)

        response = client.post(
            "/api/query",
            json={"query": "Tell me about Python", "session_id": "s1"},
        )

        assert response.json()["sources"] == sources

    def test_calls_rag_query_with_correct_arguments(self, client, mock_rag):
        """query() is invoked with the user's question and the resolved session_id."""
        mock_rag.query.return_value = ("ok", [])

        client.post(
            "/api/query",
            json={"query": "What is ML?", "session_id": "sess-42"},
        )

        mock_rag.query.assert_called_once_with("What is ML?", "sess-42")

    def test_returns_500_when_rag_raises(self, client, mock_rag):
        """A RAGSystem exception results in a 500 Internal Server Error."""
        mock_rag.query.side_effect = RuntimeError("RAG system failure")

        response = client.post(
            "/api/query",
            json={"query": "Something", "session_id": "s1"},
        )

        assert response.status_code == 500
        assert "RAG system failure" in response.json()["detail"]

    def test_returns_422_when_query_field_missing(self, client):
        """Missing required 'query' field results in a 422 Unprocessable Entity."""
        response = client.post("/api/query", json={"session_id": "s1"})

        assert response.status_code == 422

    def test_returns_422_on_empty_body(self, client):
        """Sending no body at all results in a 422 Unprocessable Entity."""
        response = client.post("/api/query", json={})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

class TestCoursesEndpoint:

    def test_returns_200_with_course_count_and_titles(self, client, mock_rag):
        """Happy path: returns total_courses and course_titles."""
        response = client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert data["total_courses"] == 2
        assert "Python 101" in data["course_titles"]
        assert "Machine Learning Basics" in data["course_titles"]

    def test_course_titles_length_matches_total_courses(self, client, mock_rag):
        """The length of course_titles matches total_courses."""
        mock_rag.get_course_analytics.return_value = {
            "total_courses": 3,
            "course_titles": ["A", "B", "C"],
        }

        response = client.get("/api/courses")
        data = response.json()

        assert data["total_courses"] == len(data["course_titles"])

    def test_returns_empty_when_no_courses_indexed(self, client, mock_rag):
        """Returns total_courses=0 and an empty list when no courses exist."""
        mock_rag.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }

        response = client.get("/api/courses")
        data = response.json()

        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_returns_500_when_analytics_raises(self, client, mock_rag):
        """A RAGSystem exception in get_course_analytics() results in 500."""
        mock_rag.get_course_analytics.side_effect = RuntimeError("DB unavailable")

        response = client.get("/api/courses")

        assert response.status_code == 500
        assert "DB unavailable" in response.json()["detail"]

    def test_calls_get_course_analytics(self, client, mock_rag):
        """The endpoint delegates to rag_system.get_course_analytics()."""
        client.get("/api/courses")

        mock_rag.get_course_analytics.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE /api/session/{session_id}
# ---------------------------------------------------------------------------

class TestDeleteSessionEndpoint:

    def test_returns_ok_on_successful_deletion(self, client):
        """DELETE /api/session/{id} returns {"status": "ok"}."""
        response = client.delete("/api/session/my-session-id")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_calls_delete_session_with_correct_id(self, client, mock_rag):
        """delete_session() is called with the session ID from the URL path."""
        client.delete("/api/session/session-xyz")

        mock_rag.session_manager.delete_session.assert_called_once_with("session-xyz")

    def test_different_session_ids_route_correctly(self, client, mock_rag):
        """Each call routes to the correct session_id from the URL."""
        client.delete("/api/session/alpha")
        client.delete("/api/session/beta")

        calls = [c.args[0] for c in mock_rag.session_manager.delete_session.call_args_list]
        assert calls == ["alpha", "beta"]
