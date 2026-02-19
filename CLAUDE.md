# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Quick start using shell script (Windows: requires Git Bash)
chmod +x run.sh
./run.sh

# Manual start
cd backend && uv run uvicorn app:app --reload --port 8888
```

> Note: `run.sh` uses port **8888** — the README mentions 8000 but the script overrides this.

### Environment Setup
```bash
# Install dependencies
uv sync

# Add new dependencies
uv add package_name

# Remove dependencies
uv remove package_name

# Environment variables required
# Create .env file with:
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### Python Execution
Always use `uv` for running Python files and commands. Never use `pip` directly.
```bash
uv run python script.py
uv run command_name
```

### Application Access
- Web Interface: http://localhost:8888
- API Documentation: http://localhost:8888/docs

## Architecture Overview

This is a Retrieval-Augmented Generation (RAG) system for course materials with a FastAPI backend and vanilla JavaScript frontend. FastAPI serves both the REST API (`/api/*`) and the static frontend as a single process.

### Core Components

**RAGSystem (backend/rag_system.py)**: Main orchestrator that coordinates all components
- Manages document ingestion, vector storage, AI generation, and search tools
- On startup, loads course documents from `docs/` — skips courses already indexed (dedup by title)
- Use `clear_existing=True` in `add_course_folder()` to force a full rebuild of the vector store

**VectorStore (backend/vector_store.py)**: ChromaDB-based vector storage with two collections
- `course_catalog`: one document per course, used for fuzzy course-name resolution
  - Metadata: title, instructor, course_link, lesson_count, lessons_json
- `course_content`: one document per text chunk, used for semantic content search
  - Metadata: course_title, lesson_number, chunk_index
- All queries resolve the course name via `course_catalog` before searching `course_content`

**AIGenerator (backend/ai_generator.py)**: Anthropic Claude API integration
- Makes two API calls per query: first to decide whether to search, second to synthesize the answer from tool results
- Tool-based RAG: Claude decides when retrieval is needed — content is not pre-fetched unconditionally
- Session history is injected as a formatted string into the system prompt (not the messages array)

**Search Tools (backend/search_tools.py)**: Tool-based search system
- `CourseSearchTool`: semantic search with optional course name and lesson number filters
- `ToolManager`: handles tool registration and execution; tracks sources from the last search

### Data Flow
1. Course documents (`.txt`, `.pdf`, `.docx`) are loaded from `docs/` on startup
2. `DocumentProcessor` extracts course metadata and splits content into sentence-based chunks
3. `VectorStore` stores metadata in `course_catalog` and chunks in `course_content`
4. User query → Claude call #1 (may invoke `search_course_content` tool) → ChromaDB search → Claude call #2 (synthesizes final answer)
5. Frontend displays the response with collapsible source attribution

### Course Document Format

Files in `docs/` must follow this structure for `DocumentProcessor` to parse them correctly:

```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 1: <title>
Lesson Link: <url>
<lesson content...>

Lesson 2: <title>
...
```

### Key Configuration (backend/config.py)
- Model: `claude-sonnet-4-20250514`
- Embedding model: `all-MiniLM-L6-v2` (SentenceTransformers, runs locally)
- Chunk size: 800 characters with 100 character overlap
- Max search results: 5 per query
- Conversation history: 2 exchange pairs per session

## Development Notes

- ChromaDB data persists across restarts in `backend/chroma_db/`
- CORS is configured with broad permissions (`allow_origins=["*"]`)
- No-cache headers are set on static files via the custom `DevStaticFiles` handler in `app.py`
