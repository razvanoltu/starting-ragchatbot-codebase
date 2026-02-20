"""
Tests for AIGenerator in backend/ai_generator.py

Covers:
- General knowledge questions are answered without calling any tool
- Course-specific questions trigger a search_course_content tool call
- Tool results are correctly included in the follow-up API call
- The second API call does NOT include tools (avoids infinite tool loops)
- Conversation history is injected into the system prompt
- When search returns an error string, Claude still produces a final response
"""

import pytest
from unittest.mock import MagicMock, patch, call

from ai_generator import AIGenerator


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------

def make_text_response(text="Direct answer."):
    """Mock Anthropic response that ends without tool use."""
    response = MagicMock()
    response.stop_reason = "end_turn"
    block = MagicMock()
    block.type = "text"
    block.text = text
    response.content = [block]
    return response


def make_tool_use_response(
    tool_name="search_course_content",
    tool_input=None,
    tool_id="toolu_abc123",
):
    """Mock Anthropic response that requests a tool call."""
    tool_input = tool_input or {"query": "test query"}
    response = MagicMock()
    response.stop_reason = "tool_use"
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = tool_name
    block.input = tool_input
    response.content = [block]
    return response


def build_generator(mock_client):
    """Instantiate AIGenerator with a patched Anthropic client."""
    with patch("ai_generator.anthropic.Anthropic", return_value=mock_client):
        return AIGenerator(api_key="test-key", model="test-model")


DUMMY_TOOLS = [
    {
        "name": "search_course_content",
        "description": "Search course materials",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }
]


# ---------------------------------------------------------------------------
# Direct (no-tool) responses
# ---------------------------------------------------------------------------

class TestDirectResponses:

    def test_general_question_answered_without_tool(self):
        """A general knowledge question gets a direct answer in a single API call."""
        client = MagicMock()
        client.messages.create.return_value = make_text_response("Paris is the capital of France.")
        gen = build_generator(client)

        result = gen.generate_response(
            query="What is the capital of France?",
            tools=DUMMY_TOOLS,
            tool_manager=MagicMock(),
        )

        assert result == "Paris is the capital of France."
        assert client.messages.create.call_count == 1  # No second call needed

    def test_response_text_is_extracted_correctly(self):
        """The text from the first content block is returned."""
        client = MagicMock()
        client.messages.create.return_value = make_text_response("Exact response text.")
        gen = build_generator(client)

        result = gen.generate_response(query="Anything", tools=None, tool_manager=None)

        assert result == "Exact response text."

    def test_no_tools_parameter_not_sent_when_tools_is_none(self):
        """When tools=None, the API call must not include a 'tools' key."""
        client = MagicMock()
        client.messages.create.return_value = make_text_response("Direct.")
        gen = build_generator(client)

        gen.generate_response(query="2+2?", tools=None, tool_manager=None)

        call_kwargs = client.messages.create.call_args[1]
        assert "tools" not in call_kwargs

    def test_conversation_history_injected_into_system_prompt(self):
        """Previous exchanges are appended to the system prompt for context."""
        client = MagicMock()
        client.messages.create.return_value = make_text_response("Follow-up.")
        gen = build_generator(client)
        history = "User: Hi\nAssistant: Hello!"

        gen.generate_response(query="Tell me more", conversation_history=history)

        call_kwargs = client.messages.create.call_args[1]
        assert history in call_kwargs["system"]


# ---------------------------------------------------------------------------
# Tool-use flow
# ---------------------------------------------------------------------------

class TestToolUseFlow:

    def test_course_question_triggers_search_tool_call(self):
        """
        Course-specific questions cause Claude to request the search tool.
        Two API calls are made: one to decide to search, one to synthesise.
        """
        client = MagicMock()
        tool_resp = make_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "what is RAG"},
            tool_id="toolu_01",
        )
        final_resp = make_text_response("RAG stands for Retrieval-Augmented Generation.")
        client.messages.create.side_effect = [tool_resp, final_resp]

        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "[RAG Course]\nRAG is a technique..."

        gen = build_generator(client)
        result = gen.generate_response(
            query="Answer this question about course materials: what is RAG?",
            tools=DUMMY_TOOLS,
            tool_manager=tool_manager,
        )

        assert client.messages.create.call_count == 2
        tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="what is RAG"
        )
        assert result == "RAG stands for Retrieval-Augmented Generation."

    def test_tool_result_included_in_second_api_call(self):
        """
        The result from tool execution is sent back to Claude as a
        tool_result message block in the second API call.
        """
        client = MagicMock()
        tool_resp = make_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "neural networks"},
            tool_id="toolu_xyz",
        )
        final_resp = make_text_response("Neural networks are layered computing systems.")
        client.messages.create.side_effect = [tool_resp, final_resp]

        tool_content = "[ML Course - Lesson 5]\nNeural networks are composed of layers."
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = tool_content

        gen = build_generator(client)
        gen.generate_response(
            query="What are neural networks?",
            tools=DUMMY_TOOLS,
            tool_manager=tool_manager,
        )

        second_call_kwargs = client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]

        # Find the user message that carries the tool result
        tool_result_msg = next(
            (m for m in messages if m["role"] == "user" and isinstance(m["content"], list)),
            None,
        )
        assert tool_result_msg is not None, "Second call must include a tool_result user message"

        result_block = tool_result_msg["content"][0]
        assert result_block["type"] == "tool_result"
        assert result_block["tool_use_id"] == "toolu_xyz"
        assert result_block["content"] == tool_content

    def test_synthesis_call_after_max_rounds_does_not_include_tools(self):
        """
        After MAX_TOOL_ROUNDS (2) tool-use rounds are exhausted, the synthesis call
        must NOT include tools. This prevents infinite tool-call loops.
        If Claude stops calling tools before the limit, the next call still includes tools
        (it had rounds remaining), but Claude chose to respond with text.
        """
        client = MagicMock()
        client.messages.create.side_effect = [
            make_tool_use_response(tool_id="toolu_r1"),
            make_tool_use_response(tool_id="toolu_r2"),
            make_text_response("Final answer."),
        ]
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Some search results."

        gen = build_generator(client)
        gen.generate_response(
            query="Course question",
            tools=DUMMY_TOOLS,
            tool_manager=tool_manager,
        )

        # Third call is the synthesis call (rounds exhausted) — must not have tools
        third_call_kwargs = client.messages.create.call_args_list[2][1]
        assert "tools" not in third_call_kwargs

    def test_assistant_tool_use_message_added_before_tool_result(self):
        """
        The conversation structure sent to Claude must be:
          user → assistant (tool_use) → user (tool_result)
        """
        client = MagicMock()
        tool_resp = make_tool_use_response(tool_id="toolu_seq")
        final_resp = make_text_response("Done.")
        client.messages.create.side_effect = [tool_resp, final_resp]

        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "Result."

        gen = build_generator(client)
        gen.generate_response(query="Course q", tools=DUMMY_TOOLS, tool_manager=tool_manager)

        second_call_kwargs = client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        roles = [m["role"] for m in messages]

        # Must contain at least: user, assistant, user (tool result)
        assert "assistant" in roles
        assistant_idx = roles.index("assistant")
        assert roles[assistant_idx + 1] == "user"


# ---------------------------------------------------------------------------
# Error propagation from the search tool
# ---------------------------------------------------------------------------

class TestSearchErrorPropagation:

    def test_search_error_still_produces_final_response(self):
        """
        When the search tool returns an error string (e.g. due to MAX_RESULTS=0),
        Claude still makes a second API call and returns a final response.
        The response will likely say it could not find the information,
        but should NOT raise an exception.
        """
        client = MagicMock()
        tool_resp = make_tool_use_response(
            tool_name="search_course_content",
            tool_input={"query": "lesson content"},
            tool_id="toolu_err",
        )
        # Claude's response after receiving an error from the search tool
        final_resp = make_text_response(
            "I was unable to retrieve the course content due to a search error."
        )
        client.messages.create.side_effect = [tool_resp, final_resp]

        tool_manager = MagicMock()
        # This is what CourseSearchTool.execute() returns when MAX_RESULTS=0
        tool_manager.execute_tool.return_value = (
            "Search error: Number of requested results 0, "
            "cannot be negative, or zero."
        )

        gen = build_generator(client)
        result = gen.generate_response(
            query="What does lesson 1 cover?",
            tools=DUMMY_TOOLS,
            tool_manager=tool_manager,
        )

        # Two calls must be made (tool use + synthesis), no exception raised
        assert client.messages.create.call_count == 2
        # The error string from the tool must have been forwarded to Claude
        second_call_kwargs = client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        tool_result_msg = next(
            (m for m in messages if m["role"] == "user" and isinstance(m["content"], list)),
            None,
        )
        tool_content = tool_result_msg["content"][0]["content"]
        assert "Search error" in tool_content

    def test_search_error_causes_uninformative_response(self):
        """
        Documents the user-visible symptom: when MAX_RESULTS=0, Claude receives
        a search error and cannot give a meaningful course-content answer.
        The response will NOT contain actual course content.
        """
        client = MagicMock()
        tool_resp = make_tool_use_response(
            tool_input={"query": "what is covered in lesson 1"},
        )
        # Claude apologises because it got an error, not real content
        final_resp = make_text_response(
            "I encountered an error while searching the course materials "
            "and cannot provide a specific answer."
        )
        client.messages.create.side_effect = [tool_resp, final_resp]

        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = (
            "Search error: Number of requested results 0, "
            "cannot be negative, or zero."
        )

        gen = build_generator(client)
        result = gen.generate_response(
            query="What is covered in lesson 1?",
            tools=DUMMY_TOOLS,
            tool_manager=tool_manager,
        )

        # The response is an apology/error message, not course content
        assert "error" in result.lower() or "unable" in result.lower() or "cannot" in result.lower()


# ---------------------------------------------------------------------------
# Sequential (multi-round) tool calling
# ---------------------------------------------------------------------------

DUMMY_TOOLS_MULTI = [
    {
        "name": "get_course_outline",
        "description": "Get course outline",
        "input_schema": {"type": "object", "properties": {"course_name": {"type": "string"}}, "required": ["course_name"]},
    },
    {
        "name": "search_course_content",
        "description": "Search course materials",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
]


class TestSequentialToolCalling:

    def test_two_rounds_make_three_api_calls(self):
        """2 tool-use rounds + 1 synthesis = 3 total API calls."""
        client = MagicMock()
        r1 = make_tool_use_response(tool_name="get_course_outline", tool_input={"course_name": "Course X"}, tool_id="toolu_r1")
        r2 = make_tool_use_response(tool_name="search_course_content", tool_input={"query": "lesson 4 topic"}, tool_id="toolu_r2")
        r3 = make_text_response("Here is the answer.")
        client.messages.create.side_effect = [r1, r2, r3]

        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = ["Outline result.", "Search result."]

        gen = build_generator(client)
        result = gen.generate_response(query="Find course covering same topic as lesson 4 of Course X", tools=DUMMY_TOOLS_MULTI, tool_manager=tool_manager)

        assert client.messages.create.call_count == 3
        assert tool_manager.execute_tool.call_count == 2
        assert result == "Here is the answer."

    def test_tools_present_in_second_call_absent_in_third(self):
        """Tools must remain in intermediate calls; stripped only for synthesis."""
        client = MagicMock()
        r1 = make_tool_use_response(tool_id="toolu_r1")
        r2 = make_tool_use_response(tool_id="toolu_r2")
        r3 = make_text_response("Done.")
        client.messages.create.side_effect = [r1, r2, r3]

        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "some result"

        gen = build_generator(client)
        gen.generate_response(query="q", tools=DUMMY_TOOLS_MULTI, tool_manager=tool_manager)

        second_call_kwargs = client.messages.create.call_args_list[1][1]
        third_call_kwargs = client.messages.create.call_args_list[2][1]
        assert "tools" in second_call_kwargs
        assert "tools" not in third_call_kwargs

    def test_messages_grow_across_both_rounds(self):
        """Synthesis call receives the full alternating conversation from both rounds."""
        client = MagicMock()
        r1 = make_tool_use_response(tool_id="toolu_r1")
        r2 = make_tool_use_response(tool_id="toolu_r2")
        r3 = make_text_response("Final.")
        client.messages.create.side_effect = [r1, r2, r3]

        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"

        gen = build_generator(client)
        gen.generate_response(query="multi-step q", tools=DUMMY_TOOLS_MULTI, tool_manager=tool_manager)

        third_call_kwargs = client.messages.create.call_args_list[2][1]
        messages = third_call_kwargs["messages"]
        roles = [m["role"] for m in messages]

        # user → assistant(r1) → user(r1 result) → assistant(r2) → user(r2 result)
        assert roles == ["user", "assistant", "user", "assistant", "user"]

        # Verify tool_use_ids are in the right tool_result messages
        assert messages[2]["content"][0]["tool_use_id"] == "toolu_r1"
        assert messages[4]["content"][0]["tool_use_id"] == "toolu_r2"

    def test_two_different_tools_called_in_sequence(self):
        """The motivating use case: get_course_outline then search_course_content."""
        client = MagicMock()
        r1 = make_tool_use_response(tool_name="get_course_outline", tool_input={"course_name": "X"}, tool_id="toolu_r1")
        r2 = make_tool_use_response(tool_name="search_course_content", tool_input={"query": "topic"}, tool_id="toolu_r2")
        r3 = make_text_response("Answer.")
        client.messages.create.side_effect = [r1, r2, r3]

        tool_manager = MagicMock()
        tool_manager.execute_tool.side_effect = ["outline data", "search data"]

        gen = build_generator(client)
        gen.generate_response(query="q", tools=DUMMY_TOOLS_MULTI, tool_manager=tool_manager)

        calls = tool_manager.execute_tool.call_args_list
        assert calls[0][0][0] == "get_course_outline"
        assert calls[1][0][0] == "search_course_content"

    def test_early_termination_when_claude_stops_after_round_one(self):
        """If Claude returns end_turn after round 1, no third API call is made."""
        client = MagicMock()
        r1 = make_tool_use_response(tool_id="toolu_r1")
        r2 = make_text_response("Done after one tool.")  # Claude stops voluntarily
        client.messages.create.side_effect = [r1, r2]

        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = "result"

        gen = build_generator(client)
        result = gen.generate_response(query="q", tools=DUMMY_TOOLS_MULTI, tool_manager=tool_manager)

        assert client.messages.create.call_count == 2
        assert tool_manager.execute_tool.call_count == 1
        assert result == "Done after one tool."

    def test_tool_error_forwarded_and_synthesis_still_produced(self):
        """A tool error string is forwarded to Claude; synthesis call still happens."""
        client = MagicMock()
        r1 = make_tool_use_response(tool_id="toolu_err")
        r2 = make_text_response("I could not find the information.")
        client.messages.create.side_effect = [r1, r2]

        error_str = "Search error: Number of requested results 0, cannot be negative, or zero."
        tool_manager = MagicMock()
        tool_manager.execute_tool.return_value = error_str

        gen = build_generator(client)
        result = gen.generate_response(query="q", tools=DUMMY_TOOLS_MULTI, tool_manager=tool_manager)

        assert client.messages.create.call_count == 2
        second_call_kwargs = client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        tool_result_msg = next(m for m in messages if m["role"] == "user" and isinstance(m["content"], list))
        assert tool_result_msg["content"][0]["content"] == error_str
        assert result == "I could not find the information."
