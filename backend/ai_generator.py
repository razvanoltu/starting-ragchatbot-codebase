import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    MAX_TOOL_ROUNDS = 2

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Tool Usage:
- **`search_course_content`**: Use for questions about specific course content or detailed educational materials
- **`get_course_outline`**: Use for questions about a course's structure, lesson list, or outline — return the course title, link, and all lesson numbers and titles
- You may make up to 2 sequential tool calls per query (e.g. first get the course outline, then search based on what you found)
- Use the minimum number of tool calls needed — do not call a tool if you already have the answer
- Each tool result is returned to you before you decide whether to call another tool
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives
- Always format URLs as markdown links with short descriptive text — e.g. **[View Course](url)** — never output bare URLs

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            
        Returns:
            Generated response as string
        """
        
        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }
        
        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        
        # Get response from Claude
        response = self.client.messages.create(**api_params)
        
        # Handle tool execution if needed
        if response.stop_reason == "tool_use" and tool_manager:
            return self._handle_tool_execution(response, api_params, tool_manager, rounds_remaining=self.MAX_TOOL_ROUNDS)
        
        # Return direct response
        return response.content[0].text
    
    def _handle_tool_execution(self, initial_response, base_params: Dict[str, Any], tool_manager, rounds_remaining: int = 1):
        """
        Handle execution of tool calls and get follow-up response.
        Supports up to MAX_TOOL_ROUNDS sequential tool-use rounds.

        Args:
            initial_response: The response containing tool use requests
            base_params: Base API parameters (includes system, messages, tools)
            tool_manager: Manager to execute tools
            rounds_remaining: How many more tool-use rounds are allowed after this one

        Returns:
            Final response text after tool execution
        """
        # Grow conversation with this round's assistant response
        messages = base_params["messages"].copy()
        messages.append({"role": "assistant", "content": initial_response.content})

        # Execute all tool calls and collect results
        tool_results = []
        for content_block in initial_response.content:
            if content_block.type == "tool_use":
                tool_result = tool_manager.execute_tool(
                    content_block.name,
                    **content_block.input
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": tool_result
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        rounds_remaining -= 1
        can_use_tools_again = rounds_remaining > 0

        # Build next API call; include tools only if another round is allowed
        next_params = {
            **self.base_params,
            "messages": messages,
            "system": base_params["system"]
        }
        if can_use_tools_again:
            next_params["tools"] = base_params["tools"]
            next_params["tool_choice"] = {"type": "auto"}

        next_response = self.client.messages.create(**next_params)

        # Recurse if Claude wants another tool AND we have rounds left
        if next_response.stop_reason == "tool_use" and can_use_tools_again:
            updated_base_params = {**base_params, "messages": messages}
            return self._handle_tool_execution(next_response, updated_base_params, tool_manager, rounds_remaining)

        # Termination: no tool_use or rounds exhausted → return text
        for block in next_response.content:
            if block.type == "text":
                return block.text
        return ""