"""GitHub MCP client for searching repositories, code, issues, and pull requests."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.mcp.base import MCPClient
from backend.utils.config import settings
from backend.utils.logger import setup_logger
import requests
import os

logger = setup_logger(__name__)


class GitHubMCP(MCPClient):
    """MCP client for searching GitHub repositories, code, issues, and pull requests."""
    
    def __init__(self):
        """Initialize GitHub MCP with API token and optional organization filter."""
        self.api_token = os.getenv("GITHUB_API_TOKEN") or getattr(settings, 'github_api_token', None)
        self.organization = os.getenv("GITHUB_ORGANIZATION") or getattr(settings, 'github_organization', None)
        self.base_url = "https://api.github.com"
        self.headers = {}
        
        if self.api_token:
            self.headers = {
                "Authorization": f"token {self.api_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            org_info = f" (org: {self.organization})" if self.organization else ""
            logger.info(f"GitHub MCP initialized with API token{org_info}")
        else:
            logger.warning("GitHub API token not found. MCP will be disabled.")
            logger.info("To enable: Set GITHUB_API_TOKEN environment variable")
    
    def get_source_type(self) -> str:
        """Return the source type identifier."""
        return "github"
    
    def is_available(self) -> bool:
        """Check if GitHub MCP is available (API token configured)."""
        return self.api_token is not None
    
    def search(self, query: str, limit: int = 10, extracted_entities: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search GitHub for code, issues, and repositories, or handle specific repository queries.
        
        Args:
            query: User query
            limit: Maximum number of results
            extracted_entities: List of entities extracted from query (for repo name detection)
        """
        if not self.is_available():
            logger.debug("GitHub MCP not available, skipping search")
            return []
        
        try:
            # Check if query is asking for a list of repositories
            if self._is_list_repositories_query(query):
                logger.info(f"Detected list repositories query, listing repositories instead of searching")
                return self._list_repositories(limit)
            
            # Check for repository information query
            repo_name = self._extract_repo_name(query, extracted_entities or [])
            if repo_name:
                # Check what type of repository query it is
                if self._is_repo_info_query(query):
                    logger.info(f"Detected repository info query for: {repo_name}")
                    return self._get_repository_info(repo_name)
                elif self._is_readme_query(query):
                    logger.info(f"Detected README query for: {repo_name}")
                    return self._get_repository_readme(repo_name)
                elif self._is_issues_query(query):
                    logger.info(f"Detected issues query for: {repo_name}")
                    return self._get_repository_issues(repo_name, limit)
                elif self._is_pull_requests_query(query):
                    logger.info(f"Detected pull requests query for: {repo_name}")
                    return self._get_repository_pull_requests(repo_name, limit)
                elif self._is_branches_query(query):
                    logger.info(f"Detected branches query for: {repo_name}")
                    return self._get_repository_branches(repo_name, limit)
                elif self._is_file_content_query(query):
                    file_path = self._extract_file_path(query, extracted_entities or [])
                    if file_path:
                        logger.info(f"Detected file content query for: {repo_name}/{file_path}")
                        return self._get_repository_file(repo_name, file_path)
            
            # Default: keyword search
            results = []
            
            # Search code
            code_results = self._search_code(query, limit // 3)
            results.extend(code_results)
            
            # Search issues
            issue_results = self._search_issues(query, limit // 3)
            results.extend(issue_results)
            
            # Search repositories
            repo_results = self._search_repositories(query, limit // 3)
            results.extend(repo_results)
            
            # Limit total results
            results = results[:limit]
            
            logger.info(f"GitHub search found {len(results)} results for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"GitHub search error: {e}")
            return []
    
    def _search_code(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search code across repositories."""
        try:
            url = f"{self.base_url}/search/code"
            
            # Build search query with organization filter if configured
            search_query = query
            if self.organization:
                search_query = f"org:{self.organization} {query}"
            
            params = {
                "q": search_query,
                "per_page": min(limit, 30)  # GitHub API max is 100, but we limit
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            items = data.get("items", [])
            
            results = []
            for item in items[:limit]:
                # Get file content snippet
                content = self._get_file_content(item.get("repository", {}).get("full_name"), item.get("path"))
                
                result = self.format_result(
                    content=content or f"Code in {item.get('path')}",
                    title=f"{item.get('repository', {}).get('full_name')}/{item.get('path')}",
                    metadata={
                        "id": f"github_code_{item.get('sha', '')}",
                        "timestamp": datetime.now().isoformat(),
                        "author": item.get("repository", {}).get("owner", {}).get("login", "unknown"),
                        "url": item.get("html_url", ""),
                        "repository": item.get("repository", {}).get("full_name", ""),
                        "path": item.get("path", ""),
                        "language": item.get("repository", {}).get("language", ""),
                        "type": "code"
                    }
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.debug(f"Error searching GitHub code: {e}")
            return []
    
    def _search_issues(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search issues and pull requests."""
        try:
            url = f"{self.base_url}/search/issues"
            
            # Build search query with organization filter if configured
            search_query = query
            if self.organization:
                # Filter to organization repositories
                search_query = f"org:{self.organization} {query}"
            
            params = {
                "q": f"{search_query} type:issue",
                "per_page": min(limit, 30),
                "sort": "updated",
                "order": "desc"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            items = data.get("items", [])
            
            results = []
            for item in items[:limit]:
                result = self.format_result(
                    content=item.get("body", "")[:1000] or item.get("title", ""),
                    title=item.get("title", "Untitled Issue"),
                    metadata={
                        "id": f"github_issue_{item.get('number', '')}",
                        "timestamp": item.get("updated_at", datetime.now().isoformat()),
                        "author": item.get("user", {}).get("login", "unknown"),
                        "url": item.get("html_url", ""),
                        "repository": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                        "number": item.get("number", ""),
                        "state": item.get("state", ""),
                        "labels": [label.get("name") for label in item.get("labels", [])],
                        "type": "issue"
                    }
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.debug(f"Error searching GitHub issues: {e}")
            return []
    
    def _search_repositories(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search repositories."""
        try:
            url = f"{self.base_url}/search/repositories"
            
            # Build search query with organization filter if configured
            search_query = query
            if self.organization:
                search_query = f"org:{self.organization} {query}"
            
            params = {
                "q": search_query,
                "per_page": min(limit, 30),
                "sort": "updated",
                "order": "desc"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            items = data.get("items", [])
            
            results = []
            for item in items[:limit]:
                result = self.format_result(
                    content=item.get("description", "")[:1000] or f"Repository: {item.get('full_name')}",
                    title=item.get("full_name", "Untitled Repository"),
                    metadata={
                        "id": f"github_repo_{item.get('id', '')}",
                        "timestamp": item.get("updated_at", datetime.now().isoformat()),
                        "author": item.get("owner", {}).get("login", "unknown"),
                        "url": item.get("html_url", ""),
                        "language": item.get("language", ""),
                        "stars": item.get("stargazers_count", 0),
                        "type": "repository"
                    }
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.debug(f"Error searching GitHub repositories: {e}")
            return []
    
    def _is_list_repositories_query(self, query: str) -> bool:
        """
        Detect if the query is asking for a list of repositories.
        
        Args:
            query: User query
            
        Returns:
            True if query is asking for a list of repositories
        """
        query_lower = query.lower()
        
        # Keywords that indicate listing repositories
        list_keywords = [
            "list repositories",
            "list repos",
            "show repositories",
            "show repos",
            "what repositories",
            "which repositories",
            "repositories do i have",
            "repositories i have access",
            "repositories i can access",
            "my repositories",
            "all repositories",
            "repositories in my github",
            "repositories on my github",
            "repositories in github"
        ]
        
        # Check if query contains list keywords
        for keyword in list_keywords:
            if keyword in query_lower:
                return True
        
        return False
    
    def _list_repositories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List repositories that the authenticated user has access to.
        
        Args:
            limit: Maximum number of repositories to return
            
        Returns:
            List of repository results
        """
        try:
            results = []
            url = None
            
            # Determine which endpoint to use
            if self.organization:
                # First try organization endpoint
                org_url = f"{self.base_url}/orgs/{self.organization}/repos"
                # Test if it's actually an organization
                test_response = requests.get(org_url, headers=self.headers, params={"per_page": 1}, timeout=5)
                
                if test_response.status_code == 200:
                    # It's an organization
                    url = org_url
                    logger.info(f"Listing repositories for organization: {self.organization}")
                elif test_response.status_code == 404:
                    # Not an organization, try as user
                    user_url = f"{self.base_url}/users/{self.organization}/repos"
                    url = user_url
                    logger.info(f"Organization not found, listing repositories for user: {self.organization}")
                else:
                    # Other error, raise it
                    test_response.raise_for_status()
            else:
                # List authenticated user's repositories (all repos user has access to)
                url = f"{self.base_url}/user/repos"
                logger.info("Listing repositories for authenticated user")
            
            if not url:
                logger.error("Could not determine repository listing endpoint")
                return []
            
            # GitHub API pagination - fetch all pages
            page = 1
            per_page = min(100, limit)  # GitHub API max is 100 per page
            
            while len(results) < limit:
                params = {
                    "page": page,
                    "per_page": per_page,
                    "sort": "updated",
                    "direction": "desc"
                }
                
                response = requests.get(url, headers=self.headers, params=params, timeout=10)
                response.raise_for_status()
                
                repos = response.json()
                
                if not repos:  # No more results
                    break
                
                for repo in repos:
                    if len(results) >= limit:
                        break
                    
                    # If organization is set, filter to only repos owned by that org/user
                    if self.organization:
                        owner = repo.get("owner", {}).get("login", "").lower()
                        if owner != self.organization.lower():
                            continue  # Skip repos not owned by the specified org/user
                    
                    # Build repository description
                    description_parts = []
                    if repo.get("description"):
                        description_parts.append(repo.get("description"))
                    
                    metadata_parts = []
                    if repo.get("language"):
                        metadata_parts.append(f"Language: {repo.get('language')}")
                    if repo.get("stargazers_count", 0) > 0:
                        metadata_parts.append(f"Stars: {repo.get('stargazers_count')}")
                    if repo.get("forks_count", 0) > 0:
                        metadata_parts.append(f"Forks: {repo.get('forks_count')}")
                    if repo.get("private"):
                        metadata_parts.append("Private")
                    else:
                        metadata_parts.append("Public")
                    
                    if metadata_parts:
                        description_parts.append(" | ".join(metadata_parts))
                    
                    content = "\n".join(description_parts) if description_parts else f"Repository: {repo.get('full_name')}"
                    
                    result = self.format_result(
                        content=content,
                        title=repo.get("full_name", "Untitled Repository"),
                        metadata={
                            "id": f"github_repo_{repo.get('id', '')}",
                            "timestamp": repo.get("updated_at", datetime.now().isoformat()),
                            "author": repo.get("owner", {}).get("login", "unknown"),
                            "url": repo.get("html_url", ""),
                            "language": repo.get("language", ""),
                            "stars": repo.get("stargazers_count", 0),
                            "forks": repo.get("forks_count", 0),
                            "private": repo.get("private", False),
                            "description": repo.get("description", ""),
                            "type": "repository"
                        }
                    )
                    results.append(result)
                
                # Check if we got fewer results than requested (last page)
                if len(repos) < per_page:
                    break
                
                page += 1
            
            logger.info(f"Listed {len(results)} repositories")
            return results
            
        except Exception as e:
            logger.error(f"Error listing GitHub repositories: {e}")
            return []
    
    def _extract_repo_name(self, query: str, extracted_entities: List[str]) -> Optional[str]:
        """
        Extract repository name from query or extracted entities.
        
        Args:
            query: User query
            extracted_entities: List of entities from query analysis
            
        Returns:
            Repository name if found, None otherwise
        """
        # First, try to find repo name in extracted entities
        # Look for entities that look like repo names (alphanumeric with dashes/underscores)
        import re
        repo_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
        
        for entity in extracted_entities:
            # Skip common words that aren't repo names
            skip_words = ['github', 'repo', 'repository', 'code', 'issue', 'pull', 'request', 'branch', 'file']
            if entity.lower() in skip_words:
                continue
            
            # Check if entity looks like a repo name
            if repo_pattern.match(entity) and len(entity) > 2:
                return entity
        
        # If not found in entities, try to extract from query
        query_lower = query.lower()
        
        # Patterns to extract repo name
        patterns = [
            r'repo\s+([a-zA-Z0-9_-]+)',
            r'repository\s+([a-zA-Z0-9_-]+)',
            r'repo\s+named\s+([a-zA-Z0-9_-]+)',
            r'repository\s+named\s+([a-zA-Z0-9_-]+)',
            r'the\s+([a-zA-Z0-9_-]+)\s+repo',
            r'the\s+([a-zA-Z0-9_-]+)\s+repository',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                repo_name = match.group(1)
                if repo_name.lower() not in ['github', 'repo', 'repository']:
                    return repo_name
        
        # Try to find capitalized/hyphenated words that might be repo names
        words = re.findall(r'\b[A-Z][a-zA-Z0-9_-]+\b', query)
        for word in words:
            if word.lower() not in ['GitHub', 'Repo', 'Repository', 'What', 'Show', 'Tell', 'Get']:
                if len(word) > 2:
                    return word
        
        return None
    
    def _extract_file_path(self, query: str, extracted_entities: List[str]) -> Optional[str]:
        """
        Extract file path from query.
        
        Args:
            query: User query
            extracted_entities: List of entities from query analysis
            
        Returns:
            File path if found, None otherwise
        """
        import re
        
        # Look for file paths in entities (files usually have extensions)
        file_pattern = re.compile(r'.*\.[a-zA-Z0-9]+$')
        for entity in extracted_entities:
            if file_pattern.match(entity):
                return entity
        
        # Extract from query patterns
        patterns = [
            r'file\s+([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)',
            r'([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)\s+file',
            r'([a-zA-Z0-9_./-]+\.(py|js|ts|json|yml|yaml|md|txt|sh|dockerfile))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _is_repo_info_query(self, query: str) -> bool:
        """Detect if query is asking for repository information."""
        query_lower = query.lower()
        info_keywords = [
            "what is the repo",
            "what is repo",
            "what is the repository",
            "what is repository",
            "tell me about repo",
            "tell me about repository",
            "repo about",
            "repository about",
            "what does repo",
            "what does repository",
            "show me details of repo",
            "show me details of repository",
            "describe repo",
            "describe repository",
            "info about repo",
            "info about repository"
        ]
        return any(keyword in query_lower for keyword in info_keywords)
    
    def _is_readme_query(self, query: str) -> bool:
        """Detect if query is asking for README."""
        query_lower = query.lower()
        readme_keywords = [
            "readme",
            "read me",
            "show readme",
            "get readme",
            "readme of",
            "readme for"
        ]
        return any(keyword in query_lower for keyword in readme_keywords)
    
    def _is_issues_query(self, query: str) -> bool:
        """Detect if query is asking for issues."""
        query_lower = query.lower()
        issues_keywords = [
            "issues in repo",
            "issues in repository",
            "issues for",
            "open issues",
            "closed issues",
            "list issues",
            "show issues",
            "what issues"
        ]
        return any(keyword in query_lower for keyword in issues_keywords) and "pull request" not in query_lower
    
    def _is_pull_requests_query(self, query: str) -> bool:
        """Detect if query is asking for pull requests."""
        query_lower = query.lower()
        pr_keywords = [
            "pull request",
            "pull requests",
            "prs",
            "pr in",
            "pr for",
            "pull requests in",
            "pull requests for"
        ]
        return any(keyword in query_lower for keyword in pr_keywords)
    
    def _is_branches_query(self, query: str) -> bool:
        """Detect if query is asking for branches."""
        query_lower = query.lower()
        branches_keywords = [
            "branches in",
            "branches for",
            "list branches",
            "show branches",
            "what branches",
            "branch in repo",
            "branch in repository"
        ]
        return any(keyword in query_lower for keyword in branches_keywords)
    
    def _is_file_content_query(self, query: str) -> bool:
        """Detect if query is asking for file content."""
        query_lower = query.lower()
        file_keywords = [
            "show file",
            "get file",
            "file in repo",
            "file in repository",
            "content of",
            "show me the",
            "get the"
        ]
        return any(keyword in query_lower for keyword in file_keywords) and any(
            ext in query_lower for ext in [".py", ".js", ".json", ".yml", ".yaml", ".md", ".txt", ".sh", "dockerfile"]
        )
    
    def _normalize_repo_name(self, repo_name: str) -> str:
        """
        Normalize repository name to full format (owner/repo).
        
        Args:
            repo_name: Repository name (may or may not include owner)
            
        Returns:
            Full repository name in format owner/repo
        """
        # If already in owner/repo format, return as is
        if '/' in repo_name:
            return repo_name
        
        # Otherwise, prepend organization/user
        if self.organization:
            return f"{self.organization}/{repo_name}"
        
        # If no organization set, try to get authenticated user
        try:
            response = requests.get(f"{self.base_url}/user", headers=self.headers, timeout=5)
            if response.status_code == 200:
                user_data = response.json()
                return f"{user_data.get('login', '')}/{repo_name}"
        except:
            pass
        
        return repo_name
    
    def _get_repository_info(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get detailed information about a repository."""
        try:
            full_repo_name = self._normalize_repo_name(repo_name)
            url = f"{self.base_url}/repos/{full_repo_name}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            repo = response.json()
            
            # Build comprehensive description
            description_parts = []
            if repo.get("description"):
                description_parts.append(repo.get("description"))
            
            metadata_parts = []
            if repo.get("language"):
                metadata_parts.append(f"Language: {repo.get('language')}")
            if repo.get("stargazers_count", 0) > 0:
                metadata_parts.append(f"Stars: {repo.get('stargazers_count')}")
            if repo.get("forks_count", 0) > 0:
                metadata_parts.append(f"Forks: {repo.get('forks_count')}")
            if repo.get("watchers_count", 0) > 0:
                metadata_parts.append(f"Watchers: {repo.get('watchers_count')}")
            if repo.get("open_issues_count", 0) > 0:
                metadata_parts.append(f"Open Issues: {repo.get('open_issues_count')}")
            if repo.get("license"):
                metadata_parts.append(f"License: {repo.get('license', {}).get('name', 'Unknown')}")
            if repo.get("topics"):
                metadata_parts.append(f"Topics: {', '.join(repo.get('topics', []))}")
            if repo.get("private"):
                metadata_parts.append("Visibility: Private")
            else:
                metadata_parts.append("Visibility: Public")
            if repo.get("created_at"):
                metadata_parts.append(f"Created: {repo.get('created_at')[:10]}")
            if repo.get("updated_at"):
                metadata_parts.append(f"Last Updated: {repo.get('updated_at')[:10]}")
            
            if metadata_parts:
                description_parts.append(" | ".join(metadata_parts))
            
            content = "\n".join(description_parts) if description_parts else f"Repository: {repo.get('full_name')}"
            
            result = self.format_result(
                content=content,
                title=f"{repo.get('full_name', repo_name)} - Repository Information",
                metadata={
                    "id": f"github_repo_info_{repo.get('id', '')}",
                    "timestamp": repo.get("updated_at", datetime.now().isoformat()),
                    "author": repo.get("owner", {}).get("login", "unknown"),
                    "url": repo.get("html_url", ""),
                    "language": repo.get("language", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "watchers": repo.get("watchers_count", 0),
                    "open_issues": repo.get("open_issues_count", 0),
                    "private": repo.get("private", False),
                    "description": repo.get("description", ""),
                    "topics": repo.get("topics", []),
                    "license": repo.get("license", {}).get("name") if repo.get("license") else None,
                    "type": "repository_info"
                }
            )
            
            logger.info(f"Retrieved repository info for: {full_repo_name}")
            return [result]
            
        except Exception as e:
            logger.error(f"Error getting repository info: {e}")
            return []
    
    def _get_repository_readme(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get README content from a repository."""
        try:
            full_repo_name = self._normalize_repo_name(repo_name)
            url = f"{self.base_url}/repos/{full_repo_name}/readme"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            readme_data = response.json()
            
            # Decode base64 content
            import base64
            content = base64.b64decode(readme_data.get("content", "")).decode('utf-8', errors='ignore')
            
            result = self.format_result(
                content=content[:5000],  # Limit to 5000 chars
                title=f"{full_repo_name} - README",
                metadata={
                    "id": f"github_readme_{readme_data.get('sha', '')}",
                    "timestamp": readme_data.get("updated_at", datetime.now().isoformat()),
                    "author": readme_data.get("author", {}).get("login", "unknown") if readme_data.get("author") else "unknown",
                    "url": readme_data.get("html_url", ""),
                    "repository": full_repo_name,
                    "path": readme_data.get("path", "README.md"),
                    "type": "readme"
                }
            )
            
            logger.info(f"Retrieved README for: {full_repo_name}")
            return [result]
            
        except Exception as e:
            logger.error(f"Error getting repository README: {e}")
            return []
    
    def _get_repository_issues(self, repo_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get issues from a repository."""
        try:
            full_repo_name = self._normalize_repo_name(repo_name)
            url = f"{self.base_url}/repos/{full_repo_name}/issues"
            
            params = {
                "state": "all",  # Get both open and closed
                "per_page": min(limit, 100),
                "sort": "updated",
                "direction": "desc"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            issues = response.json()
            # Filter out pull requests (they appear in issues endpoint too)
            issues = [issue for issue in issues if "pull_request" not in issue]
            
            results = []
            for issue in issues[:limit]:
                result = self.format_result(
                    content=issue.get("body", "")[:1000] or issue.get("title", ""),
                    title=f"#{issue.get('number')}: {issue.get('title', 'Untitled Issue')}",
                    metadata={
                        "id": f"github_issue_{issue.get('number', '')}",
                        "timestamp": issue.get("updated_at", datetime.now().isoformat()),
                        "author": issue.get("user", {}).get("login", "unknown"),
                        "url": issue.get("html_url", ""),
                        "repository": full_repo_name,
                        "number": issue.get("number", ""),
                        "state": issue.get("state", ""),
                        "labels": [label.get("name") for label in issue.get("labels", [])],
                        "type": "issue"
                    }
                )
                results.append(result)
            
            logger.info(f"Retrieved {len(results)} issues for: {full_repo_name}")
            return results
            
        except Exception as e:
            logger.error(f"Error getting repository issues: {e}")
            return []
    
    def _get_repository_pull_requests(self, repo_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pull requests from a repository."""
        try:
            full_repo_name = self._normalize_repo_name(repo_name)
            url = f"{self.base_url}/repos/{full_repo_name}/pulls"
            
            params = {
                "state": "all",  # Get both open and closed
                "per_page": min(limit, 100),
                "sort": "updated",
                "direction": "desc"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            prs = response.json()
            
            results = []
            for pr in prs[:limit]:
                result = self.format_result(
                    content=pr.get("body", "")[:1000] or pr.get("title", ""),
                    title=f"#{pr.get('number')}: {pr.get('title', 'Untitled PR')}",
                    metadata={
                        "id": f"github_pr_{pr.get('number', '')}",
                        "timestamp": pr.get("updated_at", datetime.now().isoformat()),
                        "author": pr.get("user", {}).get("login", "unknown"),
                        "url": pr.get("html_url", ""),
                        "repository": full_repo_name,
                        "number": pr.get("number", ""),
                        "state": pr.get("state", ""),
                        "labels": [label.get("name") for label in pr.get("labels", [])],
                        "merged": pr.get("merged", False),
                        "type": "pull_request"
                    }
                )
                results.append(result)
            
            logger.info(f"Retrieved {len(results)} pull requests for: {full_repo_name}")
            return results
            
        except Exception as e:
            logger.error(f"Error getting repository pull requests: {e}")
            return []
    
    def _get_repository_branches(self, repo_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get branches from a repository."""
        try:
            full_repo_name = self._normalize_repo_name(repo_name)
            url = f"{self.base_url}/repos/{full_repo_name}/branches"
            
            params = {
                "per_page": min(limit, 100)
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            branches = response.json()
            
            results = []
            for branch in branches[:limit]:
                commit = branch.get("commit", {})
                result = self.format_result(
                    content=f"Branch: {branch.get('name')}\nLast commit: {commit.get('sha', '')[:7]} - {commit.get('commit', {}).get('message', '')[:200]}",
                    title=f"Branch: {branch.get('name')}",
                    metadata={
                        "id": f"github_branch_{branch.get('name', '')}",
                        "timestamp": commit.get("commit", {}).get("author", {}).get("date", datetime.now().isoformat()),
                        "author": commit.get("commit", {}).get("author", {}).get("name", "unknown"),
                        "url": f"https://github.com/{full_repo_name}/tree/{branch.get('name')}",
                        "repository": full_repo_name,
                        "name": branch.get("name", ""),
                        "sha": commit.get("sha", ""),
                        "type": "branch"
                    }
                )
                results.append(result)
            
            logger.info(f"Retrieved {len(results)} branches for: {full_repo_name}")
            return results
            
        except Exception as e:
            logger.error(f"Error getting repository branches: {e}")
            return []
    
    def _get_repository_file(self, repo_name: str, file_path: str) -> List[Dict[str, Any]]:
        """Get file content from a repository."""
        try:
            full_repo_name = self._normalize_repo_name(repo_name)
            content = self._get_file_content(full_repo_name, file_path)
            
            if not content:
                return []
            
            result = self.format_result(
                content=content,
                title=f"{full_repo_name}/{file_path}",
                metadata={
                    "id": f"github_file_{hash(f'{full_repo_name}/{file_path}')}",
                    "timestamp": datetime.now().isoformat(),
                    "author": "unknown",
                    "url": f"https://github.com/{full_repo_name}/blob/main/{file_path}",
                    "repository": full_repo_name,
                    "path": file_path,
                    "type": "file"
                }
            )
            
            logger.info(f"Retrieved file content for: {full_repo_name}/{file_path}")
            return [result]
            
        except Exception as e:
            logger.error(f"Error getting repository file: {e}")
            return []
    
    def _get_file_content(self, repo: str, path: str) -> Optional[str]:
        """Get file content from repository."""
        try:
            url = f"{self.base_url}/repos/{repo}/contents/{path}"
            response = requests.get(url, headers=self.headers, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            if data.get("encoding") == "base64":
                import base64
                content = base64.b64decode(data.get("content", "")).decode('utf-8', errors='ignore')
                # Return first 5000 chars
                return content[:5000]
            return None
            
        except Exception as e:
            logger.debug(f"Error getting file content: {e}")
            return None


# Global GitHub MCP instance
github_mcp = GitHubMCP()
