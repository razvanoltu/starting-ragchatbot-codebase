"""
Tests for RAGSystem.query() pipeline in backend/rag_system.py

Covers:
- query() calls AIGenerator with tools registered
- Sources from search are returned alongside the response
- Sources are reset after each query (no stale data)
- Session history is read before the query and updated after
- The MAX_RESULTS=0 bug is exposed at the config level
- End-to-end simulation: zero MAX_RESULTS → search error → bad response
"""

import pytest
from unittest.mock import MagicMock, patch

from rag_system import RAGSystem
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(max_results=5, chroma_path="./test_chroma"):
    cfg = MagicMock()
    cfg.ANTHROPIC_API_KEY = "test-key"
    cfg.ANTHROPIC_MODEL = "test-model"
    cfg.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    cfg.CHUNK_SIZE = 800
    cfg.CHUNK_OVERLAP = 100
    cfg.MAX_RESULTS = max_results
    cfg.MAX_HISTORY = 2
    cfg.CHROMA_PATH = chroma_path
    return cfg


@pytest.fixture
def rag(tmp_path):
    """
    RAGSystem with all heavy dependencies (ChromaDB, Anthropic, embeddings)
    replaced by mocks. This lets us test orchestration logic in isolation.
    """
    with (
        patch("rag_system.VectorStore") as MockVectorStore,
        patch("rag_system.AIGenerator") as MockAIGen,
        patch("rag_system.DocumentProcessor"),
        patch("rag_system.SessionManager") as MockSession,
    ):
        cfg = make_config(chroma_path=str(tmp_path))
        system = RAGSystem(cfg)
        yield system, MockVectorStore.return_value, MockAIGen.return_value, MockSession.return_value


# ---------------------------------------------------------------------------
# Orchestration: AIGenerator usage
# ---------------------------------------------------------------------------

class TestQueryOrchestration:

    def test_query_calls_ai_generator(self, rag):
        """query() must delegate to AIGenerator.generate_response()."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Test response"
        mock_session.get_conversation_history.return_value = None

        response, _ = system.query("What is Python?", session_id="s1")

        mock_ai.generate_response.assert_called_once()
        assert response == "Test response"

    def test_query_passes_search_tool_definition_to_ai(self, rag):
        """query() must supply the search_course_content tool to the AI."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Response"
        mock_session.get_conversation_history.return_value = None

        system.query("Tell me about lesson 1")

        call_kwargs = mock_ai.generate_response.call_args[1]
        assert "tools" in call_kwargs
        tool_names = [t["name"] for t in call_kwargs["tools"]]
        assert "search_course_content" in tool_names

    def test_query_passes_tool_manager_to_ai(self, rag):
        """query() must pass the ToolManager so the AI can execute tools."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Response"
        mock_session.get_conversation_history.return_value = None

        system.query("Course question")

        call_kwargs = mock_ai.generate_response.call_args[1]
        assert "tool_manager" in call_kwargs
        assert call_kwargs["tool_manager"] is system.tool_manager

    def test_query_wraps_user_question_in_prompt(self, rag):
        """query() should frame the user question in the prompt sent to the AI."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Ok"
        mock_session.get_conversation_history.return_value = None

        system.query("Explain transformers")

        call_kwargs = mock_ai.generate_response.call_args[1]
        assert "Explain transformers" in call_kwargs["query"]


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionIntegration:

    def test_conversation_history_fetched_before_ai_call(self, rag):
        """query() retrieves session history and injects it into the AI call."""
        system, _, mock_ai, mock_session = rag
        history = "User: Hi\nAssistant: Hello!"
        mock_session.get_conversation_history.return_value = history
        mock_ai.generate_response.return_value = "Follow-up"

        system.query("Follow-up question", session_id="sess_abc")

        mock_session.get_conversation_history.assert_called_once_with("sess_abc")
        call_kwargs = mock_ai.generate_response.call_args[1]
        assert call_kwargs["conversation_history"] == history

    def test_exchange_added_to_session_after_response(self, rag):
        """query() saves the Q&A pair to session history after generating the answer."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Python is a language."
        mock_session.get_conversation_history.return_value = None

        system.query("What is Python?", session_id="sess_xyz")

        mock_session.add_exchange.assert_called_once_with(
            "sess_xyz", "What is Python?", "Python is a language."
        )

    def test_no_history_fetched_without_session_id(self, rag):
        """When no session_id is given, history should not be fetched."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Answer"

        system.query("Stateless question")

        mock_session.get_conversation_history.assert_not_called()


# ---------------------------------------------------------------------------
# Source attribution
# ---------------------------------------------------------------------------

class TestSourceAttribution:

    def test_sources_from_search_tool_are_returned(self, rag):
        """query() returns source links populated by the search tool."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "About ML"
        mock_session.get_conversation_history.return_value = None

        expected = [{"label": "ML Course - Lesson 1", "url": "https://example.com/1"}]
        system.search_tool.last_sources = expected

        _, sources = system.query("What is ML?")

        assert sources == expected

    def test_sources_reset_after_query(self, rag):
        """query() clears last_sources after returning them to prevent stale links."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "Response"
        mock_session.get_conversation_history.return_value = None

        system.search_tool.last_sources = [{"label": "Stale", "url": "https://stale.com"}]

        system.query("First query")

        assert system.search_tool.last_sources == []

    def test_empty_sources_returned_when_no_search_performed(self, rag):
        """When the AI answers from general knowledge (no tool call), sources are empty."""
        system, _, mock_ai, mock_session = rag
        mock_ai.generate_response.return_value = "General answer."
        mock_session.get_conversation_history.return_value = None
        system.search_tool.last_sources = []

        _, sources = system.query("What is 2+2?")

        assert sources == []


# ---------------------------------------------------------------------------
# The MAX_RESULTS=0 config bug — system-level exposure
# ---------------------------------------------------------------------------

class TestMaxResultsConfigBug:

    def test_config_max_results_is_positive(self):
        """
        FAILING TEST — this is the root cause of 'query failed'.

        config.MAX_RESULTS = 0 causes VectorStore.search() to call ChromaDB with
        n_results=0, which raises:
            TypeError: Number of requested results 0, cannot be negative, or zero.

        VectorStore catches this and returns SearchResults.empty("Search error: ...").
        CourseSearchTool.execute() returns that error string.
        AIGenerator forwards it to Claude as the tool result.
        Claude cannot answer and produces an apology / error message.
        The frontend receives this and displays 'query failed'.

        Fix: change MAX_RESULTS from 0 to 5 in backend/config.py.
        """
        from config import config

        assert config.MAX_RESULTS > 0, (
            f"BUG: config.MAX_RESULTS={config.MAX_RESULTS}. "
            "Must be >= 1. ChromaDB raises TypeError for n_results=0, "
            "which propagates as a search error and prevents any course "
            "content from being retrieved."
        )

    def test_end_to_end_simulation_with_zero_max_results(self, rag):
        """
        Simulates the full failure chain when MAX_RESULTS=0:

          1. User asks a course question.
          2. Claude calls search_course_content.
          3. VectorStore.search() returns a SearchResults.empty with an error
             (because ChromaDB rejected n_results=0).
          4. CourseSearchTool.execute() returns the error string to Claude.
          5. Claude produces an apology — not course content.

        The AI generator is mocked to behave as Claude would behave when
        it receives a search error as tool output.
        """
        system, mock_store, mock_ai, mock_session = rag
        mock_session.get_conversation_history.return_value = None

        # Simulate the real VectorStore behaviour when max_results=0:
        # search() catches the ChromaDB TypeError and returns an error result.
        mock_store.search.return_value = SearchResults.empty(
            "Search error: Number of requested results 0, "
            "cannot be negative, or zero."
        )

        # Simulate Claude's behaviour when given a search error as tool result:
        # it produces an apology rather than actual course content.
        mock_ai.generate_response.return_value = (
            "I encountered an error while searching the course materials "
            "and cannot provide a specific answer at this time."
        )

        response, sources = system.query(
            "What is covered in lesson 1 of the RAG course?", session_id="s1"
        )

        # The response is an error apology, not actual course content
        assert "error" in response.lower() or "cannot" in response.lower()
        # No sources because the search never returned real results
        assert sources == []

    def test_vector_store_search_with_zero_limit_returns_error(self):
        """
        Unit-tests VectorStore.search() directly to confirm it returns a
        SearchResults.empty(error) when ChromaDB raises TypeError for n_results=0.
        """
        with (
            patch("vector_store.chromadb.PersistentClient") as MockClient,
            patch(
                "vector_store.chromadb.utils.embedding_functions"
                ".SentenceTransformerEmbeddingFunction"
            ),
        ):
            mock_collection = MagicMock()
            mock_collection.query.side_effect = TypeError(
                "Number of requested results 0, cannot be negative, or zero."
            )
            MockClient.return_value.get_or_create_collection.return_value = mock_collection

            from vector_store import VectorStore

            store = VectorStore(
                chroma_path="/tmp/test_store",
                embedding_model="all-MiniLM-L6-v2",
                max_results=0,  # <-- the bug
            )
            results = store.search(query="anything")

        assert results.error is not None
        assert "Search error" in results.error
        assert results.is_empty()
