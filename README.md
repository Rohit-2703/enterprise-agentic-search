# Enterprise Agentic Search System

> **Project Assignment**: An intelligent enterprise search system powered by multi-agent orchestration, hybrid retrieval, and self-healing mechanisms.

## Overview

This project implements a sophisticated enterprise search system that goes beyond traditional keyword matching. It leverages **LangGraph** for agent orchestration, **OpenAI GPT-4o** for intelligent query understanding, and a hybrid retrieval system combining vector search (Pinecone) with real-time data sources (MCP clients) to provide accurate, context-aware answers across multiple enterprise data sources.

The system is designed to handle complex, multi-part queries by automatically decomposing them, routing to appropriate data sources, and synthesizing comprehensive answers with proper citations and confidence scores.

## Key Features

### Intelligent Query Processing
- **Automatic Query Decomposition**: Breaks down complex questions into manageable sub-queries
- **Typo Detection & Correction**: Automatically corrects spelling errors and grammar issues
- **Conversation Context Awareness**: Understands follow-up questions and maintains conversation history
- **Intent Recognition**: Identifies query intent (information retrieval, comparison, temporal analysis, etc.)

### Multi-Source Retrieval
- **Vector Search (Pinecone)**: Historical documents from Slack, Google Docs, Confluence, GitHub, Wiki, and CSV data
- **Real-time MCP Clients**: Live access to PostgreSQL databases, GitHub repositories, and JIRA tickets
- **Hybrid Search Strategy**: Combines semantic similarity with metadata filtering for optimal results
- **Parallel Execution**: Queries multiple sources simultaneously for faster responses

### Self-Healing & Quality Assurance
- **Confidence Scoring**: Multi-factor confidence calculation (semantic match, source authority, recency, cross-validation)
- **Automatic Query Reformulation**: Self-healing mechanism that reformulates queries when confidence is low
- **Retry Logic**: Intelligent retry with maximum attempt limits to prevent infinite loops
- **Citation Tracking**: Accurate source attribution with confidence scores for each citation

### Performance Optimization
- **Two-Tier Caching**: Redis (L1) for hot queries (<10ms) and PostgreSQL (L2) for persistent cache
- **Embedding Caching**: Reuses embeddings for similar queries to reduce API calls
- **Streaming Responses**: Real-time token-by-token answer generation for better user experience
- **Efficient Deduplication**: Removes duplicate results across multiple sources

## Architecture

### System Architecture Diagram

For a detailed visual representation of the system architecture, please refer to the architecture diagram:

**[View Architecture Diagram](YOUR_DRIVE_LINK_TO_ARCHITECTURE_DIAGRAM)**

The diagram illustrates:
- Frontend layer (Streamlit UI)
- API gateway (FastAPI)
- Agent orchestration (LangGraph workflow)
- Data retrieval layer (Pinecone + MCP clients)
- Caching layer (Redis + PostgreSQL)
- External services integration

### Video Demonstration

Watch the system in action with a comprehensive walkthrough:

**[Watch Demo Video](YOUR_DRIVE_LINK_TO_VIDEO)**

The video demonstrates:
- Query processing workflow
- Multi-source retrieval in action
- Self-healing mechanism
- Confidence scoring
- Real-time streaming responses

### High-Level Architecture

```
┌─────────────────┐
│  Streamlit UI   │  User Interface
└────────┬────────┘
         │
┌────────▼────────┐
│   FastAPI API   │  REST Endpoints + Streaming
└────────┬────────┘
         │
┌────────▼────────┐
│  LangGraph      │  Agent Orchestration
│  Workflow       │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼────┐
│Cache  │ │Agents │
│Layer  │ │       │
└───────┘ └───┬───┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───▼───┐ ┌──▼───┐ ┌───▼───┐
│Pinecone│ │ MCP  │ │OpenAI │
│Vector  │ │Clients│ │API    │
│Search  │ │       │ │       │
└───────┘ └───────┘ └───────┘
```

### Agent Workflow

The system uses an 8-agent workflow orchestrated by LangGraph:

1. **Conversation Context Agent**: Loads history and detects follow-up questions
2. **Query Analysis Agent**: Extracts intent, entities, and detects typos
3. **Query Decomposition Agent**: Breaks complex queries into sub-questions
4. **Routing Agent**: Two-stage routing (explicit detection + intelligent LLM routing)
5. **Retrieval Agent**: Executes hybrid search across multiple sources
6. **Confidence Agent**: Calculates multi-factor confidence scores
7. **Self-Healing Agent**: Reformulates queries when confidence is low
8. **Synthesis Agent**: Generates final answer with citations

## Quick Start

### Prerequisites

- Docker & Docker Compose (v20.10+)
- OpenAI API key (Paid version)
- Pinecone API key
- PostgreSQL database (included in Docker setup)
- Redis (included in Docker setup)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Rohit-2703/enterprise-agentic-search.git
   cd enterprise-agentic-search
   ```

2. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your API keys After this kill this terminal and start a new terminal and go to project root by cd enterprise-agentic-search
```

3. **Start services**
```bash
   docker-compose up --build -d
```

4. **Initialize data**
```bash
docker-compose exec backend python scripts/init_data.py
```
This command initializes the database tables, seeds PostgreSQL with mock test data (employees, sales, products, departments), and uploads the enterprise knowledge base from `data/enterprise_knowledge_base.txt` to the vector database (Pinecone).

5. **Access the application**
- **Streamlit UI**: http://localhost:8501
- **API Documentation**: http://localhost:8000/docs
- **LangSmith Monitoring**: Monitor agent workflows, traces, and performance at https://smith.langchain.com/o/enterprise-search (requires LANGCHAIN_API_KEY in .env)

## Usage Examples

### Simple Queries
```
"What is our company's vacation policy?"
"Show me product discussions from last quarter"
```

### Complex Multi-Source Queries
```
"Compare our Q3 vs Q4 performance and explain key differences"
"What technical decisions were made regarding authentication and why?"
"Show me all discussions, tickets, and code related to the new feature launch"
```

### Real-Time Queries
```
"How many employees are in the Engineering department?"
"Show me recent GitHub issues in the main repository"
"What JIRA tickets are in the current sprint?"
```

## 🔧 Technology Stack

### Core Technologies
- **LangGraph**: Agent orchestration and workflow management
- **OpenAI GPT-4o**:** LLM for query understanding and answer generation
- **OpenAI Embeddings**: text-embedding-3-small for vector embeddings
- **Pinecone**: Vector database for semantic search
- **FastAPI**: High-performance API framework
- **Streamlit**: Interactive web interface

### Data Storage
- **PostgreSQL**: Conversation history, document metadata, cache storage
- **Redis**: High-speed L1 cache for frequently accessed queries

### MCP (Model Context Protocol) Clients
- **PostgreSQL MCP**: Real-time database queries with text-to-SQL
- **GitHub MCP**: Repository, issue, and pull request search
- **JIRA MCP**: Ticket, sprint, and epic retrieval

## Performance Metrics

| Metric | Value |
|--------|-------|
| Cache Hit (Redis) | < 10ms |
| Cache Hit (PostgreSQL) | < 50ms |
| Simple Query | 2-3 seconds |
| Complex Query (3+ sub-queries) | 5-7 seconds |
| With Self-Healing | +2-3 seconds |

## Project Highlights

### What Makes This System Unique

1. **Agentic Architecture**: Uses LangGraph to orchestrate multiple specialized agents, each handling a specific aspect of query processing
2. **Hybrid Retrieval**: Combines vector search (historical data) with real-time MCP clients (live data) for comprehensive coverage
3. **Self-Healing Mechanism**: Automatically reformulates queries when confidence is low, improving answer quality
4. **Intelligent Routing**: Two-stage routing system that first checks for explicit source mentions, then uses LLM for intelligent source selection
5. **Multi-Factor Confidence**: Not just similarity scores, but a comprehensive confidence model considering semantic match, source authority, recency, and cross-validation

### Technical Challenges Solved

- **Query Complexity**: Automatic decomposition of complex queries into manageable sub-queries
- **Source Selection**: Intelligent routing to appropriate data sources based on query intent
- **Quality Assurance**: Multi-factor confidence scoring and self-healing for low-confidence results
- **Performance**: Two-tier caching system for sub-10ms response times on cached queries
- **Real-time Data**: Integration of MCP clients for live data access alongside historical vector search

## Project Structure

```
enterprise-search-ai/
├── backend/              # FastAPI backend with LangGraph agents
│   ├── agents/          # Agent implementations
│   ├── api.py           # FastAPI routes
│   ├── cache/           # Caching layer (Redis + PostgreSQL)
│   ├── database/        # Database models and connection
│   ├── mcp/             # MCP client implementations
│   ├── retrieval/       # Hybrid search and embeddings
│   └── utils/           # Utility functions
├── frontend/            # Streamlit UI
│   ├── streamlit_app.py # Main chat interface
│   └── pages/           # Additional pages (document upload)
├── data/                # Mock enterprise data
├── scripts/              # Initialization and utility scripts
├── docker-compose.yml   # Docker orchestration
└── README.md            # This file
```

## Key Components Explained

### Query Processing Pipeline

1. **User submits query** → FastAPI receives request
2. **Cache check** → Redis (L1) → PostgreSQL (L2)
3. **Agent workflow** → LangGraph orchestrates 8 agents
4. **Retrieval** → Parallel search across Pinecone + MCP sources
5. **Confidence check** → Multi-factor scoring
6. **Self-healing** (if needed) → Query reformulation and retry
7. **Synthesis** → Generate answer with citations
8. **Cache & return** → Save to cache and stream response

### Caching Strategy

- **L1 Cache (Redis)**: Hot queries, 1-hour TTL, <10ms response
- **L2 Cache (PostgreSQL)**: Persistent cache, 7-day TTL, feedback-aware
- **Cache Promotion**: L2 hits automatically promoted to L1
- **Smart Caching**: Only caches queries with confidence ≥ 0.7

### Confidence Scoring Model

```
Overall Confidence = 
  0.4 × Semantic Match Score +
  0.25 × Source Authority Score +
  0.15 × Recency Score +
  0.20 × Cross-Validation Score
```

## Future Enhancements

- [ ] User authentication and access control
- [ ] Rate limiting and API quotas
- [ ] Advanced analytics dashboard
- [ ] Support for more MCP clients (Slack, Confluence, etc.)
- [ ] Fine-tuned embedding models
- [ ] Multi-language support
- [ ] Voice query interface


