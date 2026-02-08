"""Routes queries to appropriate data sources using two-stage intelligent routing."""
from typing import Dict, List, Any, Optional
from openai import OpenAI
from backend.agents.state import AgentState
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class RoutingAgent:
    """Routes queries to appropriate data sources using two-stage routing (explicit detection + intelligent routing)."""
    
    PINECONE_SOURCES = [
        "slack",
        "google_docs",
        "confluence",
        "github",
        "wiki",
        "csv_data"
    ]
    
    MCP_SOURCES = [
        "postgresql_mcp",
        "github_mcp",
        "jira_mcp"
    ]
    
    DATA_SOURCES = PINECONE_SOURCES + MCP_SOURCES
    
    REALTIME_KEYWORDS = [
        "latest", "recent", "current", "today", "now", "this week",
        "yesterday", "last night", "just", "new", "updated"
    ]
    
    def __init__(self):
        """Initialize the OpenAI client for routing decisions."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    def route(self, state: AgentState) -> AgentState:
        """Route each sub-query to appropriate data sources using two-stage routing."""
        queries = state.get("decomposed_queries", [state["original_query"]])
        logger.info(f"Routing {len(queries)} queries to data sources")
        
        routing = {}
        
        for query in queries:
            routing_plan = self._route_single_query(query, state.get("query_intent"))
            routing[query] = routing_plan
        
        state["source_routing"] = routing
        state["processing_steps"].append(
            f"Routing: Mapped queries to data sources"
        )
        
        logger.info(f"Routing complete: {routing}")
        return state
    
    def _combined_routing(self, query: str, intent: Optional[str] = None) -> Dict[str, Any]:
        """Combined routing that performs both explicit detection and intelligent routing in a single LLM call."""
        query_lower = query.lower()
        is_realtime = any(keyword in query_lower for keyword in self.REALTIME_KEYWORDS)
        
        historical_keywords = ["q4 2024", "q3 2024", "last quarter", "last year", "2023", "2024", "historical"]
        is_historical = any(keyword in query_lower for keyword in historical_keywords)
        
        prompt = f"""Analyze this query and determine the best data sources and execution strategy.
Perform BOTH explicit source detection AND intelligent routing in your analysis.

Query: "{query}"
Intent: {intent or "unknown"}
Temporal context: Real-time={is_realtime}, Historical={is_historical}

Available sources:

INDEXED SOURCES (Pinecone - historical/archived data):
- slack: Team communications, discussions, announcements
- google_docs: Documents, specs, reports, strategies (indexed historical)
- confluence: Technical documentation, wikis, runbooks
- github: Code, issues, pull requests, technical decisions
- wiki: Company policies, FAQs, guides
- csv_data: Structured data, metrics, sales data

REAL-TIME SOURCES (MCP - live/current data):
- postgresql_mcp: Real-time access to structured company data (employees, products, sales, etc.)
- github_mcp: Real-time access to code repositories, issues, pull requests
- jira_mcp: Real-time access to project management tickets, issues, epics, sprints

IMPORTANT CONTEXT RULES for explicit detection:
- "GitHub issues" or "issues in GitHub" → github_mcp (NOT jira_mcp)
- "JIRA issues" or "issues in JIRA" → jira_mcp (NOT github_mcp)
- "issues" alone without context → Use intelligent routing
- "database" or "SQL" → postgresql_mcp
- "code" or "repository" → github_mcp
- "ticket" or "sprint" → jira_mcp

Routing Analysis:
1. First, check if query EXPLICITLY mentions data sources:
   - If yes, set is_explicit=true and use those sources
   - If no, set is_explicit=false and proceed with intelligent routing

2. Temporal Analysis:
   - Historical queries (Q4 2024, last year) → Prioritize Pinecone sources
   - Real-time queries (latest, current, today) → Include BOTH MCP sources AND Pinecone sources
   - Mixed temporal → Use BOTH Pinecone and MCP

3. Data Type Analysis:
   - Policy/document queries → wiki, google_docs
   - Code/technical queries → github, github_mcp, confluence
   - Project management queries → jira_mcp
   - Communication queries → slack
   - Structured data queries → csv_data, postgresql_mcp
   - Employee/organizational queries → postgresql_mcp
   - Bug/ticket queries → jira_mcp
   - Mixed/complex queries → Multiple sources

4. IMPORTANT: Always include Pinecone sources (wiki, google_docs, csv_data, etc.) unless query explicitly mentions a specific source.
   Pinecone contains enterprise data and should be searched alongside MCP sources for comprehensive coverage.

5. Execution Strategy:
   - "parallel": Use when sources are independent and query needs comprehensive coverage (recommended for most queries)
   - "sequential": Use when query suggests a primary source with fallback
   - "fallback": Use when query is ambiguous or needs to try sources one by one

Respond in JSON format:
{{
  "is_explicit": true/false,  // true if query explicitly mentions data sources
  "explicit_sources": ["source1", "source2", ...],  // Sources explicitly mentioned (empty if not explicit)
  "sources": ["source1", "source2"],  // Final list of sources to use (includes explicit + intelligent routing)
  "execution_strategy": "parallel" | "sequential" | "fallback",
  "primary_source": "source1" (if sequential/fallback, null if parallel),
  "secondary_sources": ["source2"] (if sequential/fallback, empty if parallel),
  "reasoning": "Brief explanation of detection and routing decision",
  "expected_data_types": ["documents", "code", "structured", "communications"]
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing queries to identify explicit data source mentions and perform intelligent routing. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            from backend.utils.json_parser import extract_json_from_response
            content = response.choices[0].message.content
            routing = extract_json_from_response(content)
            
            if not routing:
                raise ValueError("Failed to parse JSON from response")
            
            is_explicit = routing.get("is_explicit", False)
            explicit_sources = routing.get("explicit_sources", [])
            sources = routing.get("sources", [])
            execution_strategy = routing.get("execution_strategy", "parallel")
            primary_source = routing.get("primary_source")
            secondary_sources = routing.get("secondary_sources", [])
            reasoning = routing.get("reasoning", "Combined routing decision")
            
            valid_sources = [s for s in sources if s in self.DATA_SOURCES]
            
            if is_explicit and explicit_sources:
                valid_explicit = [s for s in explicit_sources if s in self.DATA_SOURCES]
                if valid_explicit:
                    valid_sources = valid_explicit.copy()
                    for pinecone_source in ["wiki", "google_docs", "csv_data"]:
                        if pinecone_source not in valid_sources:
                            valid_sources.append(pinecone_source)
            
            pinecone_sources_included = [s for s in valid_sources if s in self.PINECONE_SOURCES]
            
            if not pinecone_sources_included:
                default_pinecone = ["wiki", "google_docs", "csv_data"]
                for pinecone_source in default_pinecone:
                    if pinecone_source not in valid_sources:
                        valid_sources.append(pinecone_source)
                logger.info(f"Added Pinecone sources to ensure enterprise data coverage: {default_pinecone}")
            
            if not valid_sources:
                if is_realtime:
                    valid_sources = ["postgresql_mcp", "github_mcp", "jira_mcp"] + ["wiki", "google_docs", "csv_data"]
                    execution_strategy = "parallel"
                elif is_historical:
                    valid_sources = self.PINECONE_SOURCES[:4]
                    execution_strategy = "parallel"
                else:
                    valid_sources = ["wiki", "google_docs", "csv_data"]
                    execution_strategy = "parallel"
            
            if is_explicit and len(valid_sources) == 1:
                execution_strategy = "sequential"
                primary_source = valid_sources[0]
                secondary_sources = []
            elif is_explicit and len(valid_sources) > 1:
                has_multiple_mentions = any(
                    phrase in query_lower 
                    for phrase in [" and ", " both ", " also check ", " plus ", " along with ", " can you give me"]
                )
                if has_multiple_mentions:
                    execution_strategy = "parallel"
                    primary_source = None
                    secondary_sources = []
                else:
                    execution_strategy = "sequential"
                    primary_source = valid_sources[0]
                    secondary_sources = valid_sources[1:]
            
            if primary_source and primary_source not in valid_sources:
                primary_source = valid_sources[0] if valid_sources else None
            
            secondary_sources = [s for s in secondary_sources if s in valid_sources and s != primary_source]
            
            routing_plan = {
                "sources": valid_sources,
                "execution_strategy": execution_strategy,
                "primary_source": primary_source,
                "secondary_sources": secondary_sources,
                "reasoning": reasoning,
                "explicit_detection": is_explicit
            }
            
            logger.info(f"Combined routing: {valid_sources} (strategy: {execution_strategy}, explicit: {is_explicit})")
            return routing_plan
            
        except Exception as e:
            logger.error(f"Combined routing error: {e}")
            return {
                "sources": ["wiki", "google_docs", "csv_data", "postgresql_mcp"],
                "execution_strategy": "parallel",
                "primary_source": None,
                "secondary_sources": [],
                "reasoning": "Fallback routing due to error",
                "explicit_detection": False
            }
    
    def _route_single_query(self, query: str, intent: Optional[str] = None) -> Dict[str, Any]:
        """Route a single query using combined intelligent routing."""
        return self._combined_routing(query, intent)


def routing_node(state: AgentState) -> AgentState:
    """LangGraph node for routing."""
    agent = RoutingAgent()
    return agent.route(state)
