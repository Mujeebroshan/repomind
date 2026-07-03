# 🧠 RepoMind

**AI-powered deep codebase understanding agent.**

RepoMind reads every file in a repository, builds hierarchical understanding (file → directory → component → project), maps dependency graphs, and uses that deep context to answer questions, suggest improvements, and generate code.

Uses **Ollama for local/free bulk processing** and free cloud APIs (Gemini, Groq, OpenRouter) for complex reasoning tasks.

---

## ✨ Features

| Feature | Description |
|---|---|
| **🌳 AST Parsing** | Tree-sitter powered semantic code parsing for Python, JavaScript, TypeScript, Go, Rust, Java, C/C++ |
| **📊 Dependency Graph** | NetworkX-based import/call graph with PageRank importance scoring |
| **🧠 Hierarchical Understanding** | Bottom-up summaries: file → directory → project overview |
| **🔍 Hybrid Retrieval** | Vector search + knowledge base + dependency graph for rich context |
| **💬 Smart Chat** | Ask questions about any repo — answers grounded in actual code |
| **✨ Code Generation** | Generate code that matches the project's patterns and conventions |
| **💡 Suggestions** | Proactive improvement suggestions based on detected patterns |
| **🗺️ Repo Map** | Aider-style compact structural overview ranked by importance |
| **🔀 Smart Routing** | Auto-routes simple questions to local LLM, complex ones to cloud |
| **💰 Cost Tracking** | See how much you've saved by running locally |

---

## 🚀 Quick Start

### 1. Prerequisites

- **Python 3.10+**
- **Ollama** running locally with models:
  ```bash
  ollama pull qwen2.5-coder:7b
  ollama pull nomic-embed-text
  ```

### 2. Install

```bash
cd repomind
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your API keys (optional, for cloud escalation)
```

### 4. Run

```bash
repomind serve
# Opens browser at http://localhost:8420
```

---

## 🖥️ CLI Reference

```bash
# Start the web UI
repomind serve [--host 127.0.0.1] [--port 8420] [--no-browser]

# Analyze a repository
repomind analyze /path/to/repo [--depth quick|standard|deep]

# View summary
repomind summary /path/to/repo [--level project|directory|file] [--path specific/path]
```

### Analysis Depths

| Depth | What it does | Speed |
|---|---|---|
| `quick` | File-level summaries only | Fast |
| `standard` | Files + directories + project overview | Medium |
| `deep` | Everything + pattern extraction + cloud escalation | Slow |

---

## 🏗️ Architecture

```
repomind/
├── parser/           # AST parsing & smart chunking
│   ├── languages.py  # Tree-sitter grammar registry
│   ├── ast_parser.py # Semantic code extraction
│   └── smart_chunker.py  # Symbol-boundary chunking
├── graph/            # Dependency graph
│   ├── builder.py    # NetworkX graph construction
│   └── query.py      # Graph queries & PageRank
├── understanding/    # Hierarchical understanding
│   ├── knowledge_base.py  # Persistent KB store
│   ├── summarizer.py      # LLM summarization
│   ├── pattern_extractor.py  # Pattern detection
│   └── analyzer.py        # Pipeline orchestrator
├── retrieval/        # Hybrid retrieval
│   ├── hybrid_retriever.py  # Vector+KB+graph retrieval
│   └── repo_map.py          # Compact repo map
├── generation/       # Code generation
│   ├── code_generator.py  # Context-rich code gen
│   ├── scaffold.py        # Project scaffolding
│   └── suggestions.py    # Improvement suggestions
├── providers/        # LLM provider abstraction
│   ├── ollama_provider.py
│   ├── gemini_provider.py
│   ├── anthropic_provider.py
│   └── openai_compatible.py  # OpenAI, Groq, OpenRouter
├── api.py           # FastAPI endpoints
├── chat_engine.py   # RAG chat orchestration
├── router.py        # Smart routing (local vs cloud)
├── config.py        # Configuration management
└── cli.py           # CLI entry point
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/workspace` | Open a repository workspace |
| POST | `/api/index` | Start vector embedding |
| GET | `/api/index/status` | Check indexing progress |
| POST | `/api/analyze` | Start deep analysis pipeline |
| GET | `/api/analyze/status` | Check analysis progress |
| POST | `/api/chat` | Chat with SSE streaming |
| GET | `/api/knowledge` | Query knowledge base |
| GET | `/api/graph` | Get dependency graph |
| GET | `/api/repomap` | Get compact repo map |
| POST | `/api/generate/code` | Generate code |
| GET | `/api/suggestions` | Get improvement suggestions |
| GET | `/api/stats` | Usage statistics |
| GET/POST | `/api/settings` | Manage settings |

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOCAL_BACKEND` | `ollama` | `ollama` or `lmstudio` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `LOCAL_CHAT_MODEL` | `qwen2.5-coder:7b` | Model for chat/summaries |
| `LOCAL_EMBED_MODEL` | `nomic-embed-text` | Model for embeddings |
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `GROQ_API_KEY` | - | Groq API key |
| `OPENROUTER_API_KEY` | - | OpenRouter API key |
| `ANALYSIS_DEPTH` | `standard` | Default analysis depth |
| `MAX_CONCURRENT_SUMMARIES` | `4` | Parallel summary requests |
| `USE_CLOUD_FOR_PROJECT_SUMMARY` | `true` | Use cloud for project overview |

---

## 📄 License

MIT License — see [LICENSE](LICENSE).
