"""MCP (Model Context Protocol) clients for real-time data sources."""
from backend.mcp.base import MCPClient
from backend.mcp.postgresql import postgresql_mcp, PostgreSQLMCP
from backend.mcp.github import github_mcp, GitHubMCP
from backend.mcp.jira import jira_mcp, JiraMCP

__all__ = [
    "MCPClient",
    "postgresql_mcp",
    "PostgreSQLMCP",
    "github_mcp",
    "GitHubMCP",
    "jira_mcp",
    "JiraMCP"
]
