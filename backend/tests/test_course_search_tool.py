"""
Tests for CourseSearchTool.execute() in backend/search_tools.py

Covers:
- Correct result formatting when the vector store returns content
- Error propagation when the vector store fails (e.g. due to n_results=0)
- "No content found" message when results are empty
- Filter forwarding (course_name, lesson_number)
- Source tracking (last_sources population)
- The MAX_RESULTS=0 config bug that causes all searches to fail
"""

import pytest
from unittest.mock import MagicMock

from search_tools import CourseSearchTool
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_store():
    """Return a VectorStore mock with neutral defaults."""
    store = MagicMock()
    store.get_lesson_link.return_value = None
    store.get_course_link.return_value = None
    return store


def ok_results(docs, metas):
    """Build a successful SearchResults from raw lists."""
    distances = [0.1] * len(docs)
    return SearchResults(documents=docs, metadata=metas, distances=distances)


def err_results(msg):
    """Build an error SearchResults."""
    return SearchResults.empty(msg)


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

class TestExecuteFormatting:

    def test_returns_course_title_and_lesson_in_output(self):
        """Formatted output contains the course title and lesson number."""
        store = make_mock_store()
        store.search.return_value = ok_results(
            docs=["Python is a high-level programming language."],
            metas=[{"course_title": "Python 101", "lesson_number": 1}],
        )
        tool = CourseSearchTool(store)

        result = tool.execute(query="What is Python?")

        assert "Python 101" in result
        assert "Lesson 1" in result
        assert "Python is a high-level programming language." in result

    def test_all_returned_documents_appear_in_output(self):
        """Every document returned by the store is included in the output."""
        store = make_mock_store()
        store.search.return_value = ok_results(
            docs=["First chunk content.", "Second chunk content."],
            metas=[
                {"course_title": "ML Course", "lesson_number": 1},
                {"course_title": "ML Course", "lesson_number": 2},
            ],
        )
        tool = CourseSearchTool(store)

        result = tool.execute(query="machine learning")

        assert "First chunk content." in result
        assert "Second chunk content." in result
        # Both lesson headers should appear
        assert result.count("ML Course") == 2

    def test_result_without_lesson_number_omits_lesson_label(self):
        """If metadata has no lesson_number, the output has no 'Lesson N' label."""
        store = make_mock_store()
        store.search.return_value = ok_results(
            docs=["General course overview content."],
            metas=[{"course_title": "Intro Course", "lesson_number": None}],
        )
        tool = CourseSearchTool(store)

        result = tool.execute(query="overview")

        assert "Intro Course" in result
        assert "Lesson" not in result


# ---------------------------------------------------------------------------
# Error / empty handling
# ---------------------------------------------------------------------------

class TestExecuteErrorHandling:

    def test_returns_error_string_when_store_reports_error(self):
        """execute() surfaces the vector store error message directly."""
        store = make_mock_store()
        store.search.return_value = err_results(
            "Search error: Number of requested results 0, cannot be negative, or zero."
        )
        tool = CourseSearchTool(store)

        result = tool.execute(query="What is Python?")

        assert "Search error" in result
        assert "0" in result  # The n_results=0 detail should be visible

    def test_returns_no_results_message_when_results_empty(self):
        """execute() returns a clear message when the search yields nothing."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        result = tool.execute(query="nonexistent topic")

        assert "No relevant content found" in result

    def test_no_results_message_includes_course_filter(self):
        """The empty-results message names the course filter that was applied."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        result = tool.execute(query="anything", course_name="Python 101")

        assert "No relevant content found" in result
        assert "Python 101" in result

    def test_no_results_message_includes_lesson_filter(self):
        """The empty-results message names the lesson filter that was applied."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        result = tool.execute(query="anything", lesson_number=3)

        assert "No relevant content found" in result
        assert "3" in result


# ---------------------------------------------------------------------------
# Filter forwarding
# ---------------------------------------------------------------------------

class TestExecuteFilterForwarding:

    def test_passes_query_to_store(self):
        """execute() forwards the query string to VectorStore.search()."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        tool.execute(query="neural networks explained")

        store.search.assert_called_once()
        kwargs = store.search.call_args.kwargs
        assert kwargs["query"] == "neural networks explained"

    def test_passes_course_name_filter_to_store(self):
        """execute() forwards course_name to VectorStore.search()."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        tool.execute(query="backpropagation", course_name="Deep Learning 101")

        store.search.assert_called_once_with(
            query="backpropagation",
            course_name="Deep Learning 101",
            lesson_number=None,
        )

    def test_passes_lesson_number_filter_to_store(self):
        """execute() forwards lesson_number to VectorStore.search()."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        tool.execute(query="intro content", lesson_number=2)

        store.search.assert_called_once_with(
            query="intro content",
            course_name=None,
            lesson_number=2,
        )

    def test_passes_both_filters_together(self):
        """execute() forwards course_name AND lesson_number simultaneously."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        tool.execute(query="transformer attention", course_name="NLP", lesson_number=5)

        store.search.assert_called_once_with(
            query="transformer attention",
            course_name="NLP",
            lesson_number=5,
        )


# ---------------------------------------------------------------------------
# Source tracking
# ---------------------------------------------------------------------------

class TestExecuteSourceTracking:

    def test_last_sources_populated_after_successful_search(self):
        """execute() stores source info for each result so the UI can render links."""
        store = make_mock_store()
        store.search.return_value = ok_results(
            docs=["Transformer content"],
            metas=[{"course_title": "NLP Course", "lesson_number": 3}],
        )
        store.get_lesson_link.return_value = "https://example.com/lesson/3"
        tool = CourseSearchTool(store)

        tool.execute(query="transformers")

        assert len(tool.last_sources) == 1
        assert tool.last_sources[0]["label"] == "NLP Course - Lesson 3"
        assert tool.last_sources[0]["url"] == "https://example.com/lesson/3"

    def test_falls_back_to_course_link_when_no_lesson_link(self):
        """execute() uses the course link when the lesson has no dedicated URL."""
        store = make_mock_store()
        store.search.return_value = ok_results(
            docs=["General content."],
            metas=[{"course_title": "My Course", "lesson_number": None}],
        )
        store.get_lesson_link.return_value = None
        store.get_course_link.return_value = "https://example.com/my-course"
        tool = CourseSearchTool(store)

        tool.execute(query="general info")

        assert tool.last_sources[0]["url"] == "https://example.com/my-course"

    def test_last_sources_empty_when_no_results(self):
        """execute() does not populate last_sources if the search returned nothing."""
        store = make_mock_store()
        store.search.return_value = ok_results(docs=[], metas=[])
        tool = CourseSearchTool(store)

        tool.execute(query="nothing")

        assert tool.last_sources == []

    def test_last_sources_empty_when_store_errors(self):
        """execute() does not populate last_sources when the store returns an error."""
        store = make_mock_store()
        store.search.return_value = err_results("Search error: something went wrong")
        tool = CourseSearchTool(store)

        tool.execute(query="whatever")

        assert tool.last_sources == []

    def test_multiple_results_produce_multiple_sources(self):
        """Each result document gets its own source entry."""
        store = make_mock_store()
        store.search.return_value = ok_results(
            docs=["Doc A", "Doc B"],
            metas=[
                {"course_title": "Course X", "lesson_number": 1},
                {"course_title": "Course X", "lesson_number": 2},
            ],
        )
        tool = CourseSearchTool(store)

        tool.execute(query="content")

        assert len(tool.last_sources) == 2


# ---------------------------------------------------------------------------
# The MAX_RESULTS=0 config bug
# ---------------------------------------------------------------------------

class TestMaxResultsConfigBug:

    def test_config_max_results_must_be_positive(self):
        """
        FAILING TEST — reveals the root cause of 'query failed'.

        config.MAX_RESULTS is currently set to 0. ChromaDB raises:
            TypeError: Number of requested results 0, cannot be negative, or zero.

        VectorStore.search() catches this and returns SearchResults.empty(error).
        CourseSearchTool.execute() then returns the error string as tool output.
        Claude receives an error instead of course content and cannot answer,
        which the frontend displays as 'query failed'.

        Fix: set MAX_RESULTS to a positive integer (e.g. 5) in config.py.
        """
        from config import config

        assert config.MAX_RESULTS > 0, (
            f"BUG: config.MAX_RESULTS={config.MAX_RESULTS}. "
            "ChromaDB requires n_results >= 1. "
            "All content searches fail silently with this setting, "
            "causing the chatbot to return errors for every course-specific query."
        )

    def test_search_tool_returns_error_when_store_gets_zero_n_results(self):
        """
        Simulates what happens at runtime with MAX_RESULTS=0.

        The store raises a TypeError (as ChromaDB does), VectorStore wraps it
        in SearchResults.empty(), and CourseSearchTool.execute() returns the
        error string — which becomes the tool result Claude has to work with.
        """
        store = make_mock_store()
        # Reproduce the exact ChromaDB error message
        store.search.return_value = err_results(
            "Search error: Number of requested results 0, "
            "cannot be negative, or zero."
        )
        tool = CourseSearchTool(store)

        result = tool.execute(query="What is covered in lesson 1?")

        # The tool is returning an error, not course content.
        # Claude cannot answer the question from this output.
        assert "Search error" in result
        assert "No relevant content found" not in result  # No content at all
