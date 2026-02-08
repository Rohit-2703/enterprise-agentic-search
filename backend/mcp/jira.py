"""JIRA MCP client for searching issues, tickets, and project management data."""

from typing import List, Dict, Any
from datetime import datetime
from backend.mcp.base import MCPClient
from backend.utils.config import settings
from backend.utils.logger import setup_logger
import requests
import os
from requests.auth import HTTPBasicAuth

logger = setup_logger(__name__)


class JiraMCP(MCPClient):
    """MCP client for searching JIRA issues and tickets."""

    def __init__(self):
        """Initialize JIRA MCP with credentials from environment variables."""
        self.jira_url = os.getenv("JIRA_URL")
        self.jira_email = os.getenv("JIRA_EMAIL")
        self.api_token = os.getenv("JIRA_API_TOKEN")

        if self.jira_url and self.jira_email and self.api_token:
            self.jira_url = self.jira_url.rstrip("/")
            self.auth = HTTPBasicAuth(self.jira_email, self.api_token)
            logger.info(f"JIRA MCP initialized for {self.jira_url}")
        else:
            self.auth = None
            logger.warning("JIRA credentials not found. MCP disabled.")

    def get_source_type(self) -> str:
        """Return the source type identifier."""
        return "jira"

    def is_available(self) -> bool:
        """Check if JIRA credentials are valid by testing authentication."""
        if not self.auth:
            return False

        try:
            url = f"{self.jira_url}/rest/api/3/myself"
            r = requests.get(
                url,
                auth=self.auth,
                headers={"Accept": "application/json"},
                timeout=5,
            )
            return r.status_code == 200
        except Exception:
            return False
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search JIRA issues using the new JIRA Cloud API endpoint."""
        if not self.is_available():
            logger.warning("JIRA MCP unavailable (auth or connectivity issue)")
            return [self._permission_error_result()]

        try:
            jql = self._build_jql(query)

            url = f"{self.jira_url}/rest/api/3/search/jql"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            payload = {
                "jql": jql,
                "maxResults": min(limit, 50),
                "fields": [
                    "summary",
                    "description",
                    "status",
                    "assignee",
                    "reporter",
                    "created",
                    "updated",
                    "project",
                    "issuetype",
                    "priority",
                    "labels",
                    "components",
                    "fixVersions",
                    "resolution",
                    "resolutiondate",
                ],
            }

            response = requests.post(
                url,
                auth=self.auth,
                headers=headers,
                json=payload,
                timeout=15,
            )

            if response.status_code in (401, 403):
                logger.error("JIRA authentication/permission error")
                return [self._permission_error_result()]

            if response.status_code == 410:
                logger.error("JIRA search endpoint deprecated/misused")
                return [self._permission_error_result()]

            response.raise_for_status()
            data = response.json()


            issues = data.get("issues", [])
            results = []

            for issue in issues[:limit]:
                fields = issue.get("fields", {})

                summary = fields.get("summary", "No summary")
                description = self._extract_description(fields.get("description"))

                assignee = fields.get("assignee") or {}
                reporter = fields.get("reporter") or {}
                priority = fields.get("priority") or {}
                status = fields.get("status") or {}
                project = fields.get("project") or {}
                issuetype = fields.get("issuetype") or {}
                resolution = fields.get("resolution") or {}
                components = fields.get("components", [])
                labels = fields.get("labels", [])
                fix_versions = fields.get("fixVersions", [])

                # Build comprehensive content for various query types
                content_parts = [
                    f"Issue Key: {issue.get('key')}",
                    f"Summary: {summary}",
                    f"Project: {project.get('name', 'Unknown')}",
                    f"Issue Type: {issuetype.get('name', 'Unknown')}",
                    f"Status: {status.get('name', 'Unknown')}",
                ]

                # Dates (for "when was X created/updated" queries)
                created = fields.get("created")
                if created:
                    content_parts.append(f"Created: {created}")
                    content_parts.append(f"Created By: {reporter.get('displayName', 'Unknown')}")

                updated = fields.get("updated")
                if updated:
                    content_parts.append(f"Last Updated: {updated}")

                resolution_date = fields.get("resolutiondate")
                if resolution_date:
                    content_parts.append(f"Resolved: {resolution_date}")
                    if resolution.get("name"):
                        content_parts.append(f"Resolution: {resolution.get('name')}")

                # Priority (for "high priority issues" queries)
                if priority.get("name"):
                    content_parts.append(f"Priority: {priority.get('name')}")

                # Assignee (for "issues assigned to X" queries)
                if assignee.get("displayName"):
                    content_parts.append(f"Assignee: {assignee.get('displayName')}")
                    content_parts.append(f"Assignee Email: {assignee.get('emailAddress', 'N/A')}")
                else:
                    content_parts.append("Assignee: Unassigned")

                # Labels (for "issues with label X" queries)
                if labels:
                    content_parts.append(f"Labels: {', '.join(labels)}")

                # Components (for "issues in component X" queries)
                if components:
                    component_names = [comp.get("name", "") for comp in components if comp.get("name")]
                    if component_names:
                        content_parts.append(f"Components: {', '.join(component_names)}")

                # Fix Versions (for "issues in version X" queries)
                if fix_versions:
                    version_names = [v.get("name", "") for v in fix_versions if v.get("name")]
                    if version_names:
                        content_parts.append(f"Fix Versions: {', '.join(version_names)}")

                # Description (for content search)
                if description:
                    content_parts.append(f"\nDescription:\n{description[:500]}")


                # Build metadata with all important fields
                metadata = {
                    "id": f"jira_{issue.get('key')}",
                    "key": issue.get("key"),
                    "status": status.get("name", ""),
                    "project": project.get("name", ""),
                    "issue_type": issuetype.get("name", ""),
                    "priority": priority.get("name", ""),
                    "author": assignee.get("displayName", "Unassigned"),
                    "assignee_email": assignee.get("emailAddress", ""),
                    "reporter": reporter.get("displayName", ""),
                    "created": fields.get("created"),
                    "updated": fields.get("updated"),
                    "timestamp": fields.get("updated", datetime.utcnow().isoformat()),
                    "resolution": resolution.get("name", "") if resolution else "",
                    "resolutiondate": fields.get("resolutiondate", ""),
                    "url": f"{self.jira_url}/browse/{issue.get('key')}",
                    "type": "issue",
                }
                
                # Add labels, components, fix versions to metadata if available
                if labels:
                    metadata["labels"] = labels
                if components:
                    metadata["components"] = [comp.get("name", "") for comp in components if comp.get("name")]
                if fix_versions:
                    metadata["fix_versions"] = [v.get("name", "") for v in fix_versions if v.get("name")]

                results.append(
                    self.format_result(
                        title=f"{issue.get('key')}: {summary}",
                        content="\n".join(content_parts),
                        metadata=metadata,
                    )
                )


            logger.info(f"JIRA search returned {len(results)} results")
            return results

        except Exception as e:
            logger.exception(f"JIRA search failed: {e}")
            return [self._permission_error_result()]

    # ------------------------------------------------------------------
    # JQL GENERATION
    # ------------------------------------------------------------------

    def _build_jql(self, query: str) -> str:
        """Convert natural language → valid JQL using LLM."""
        from openai import OpenAI
        from backend.utils.json_parser import extract_json_from_response

        client = OpenAI(api_key=settings.openai_api_key)

        prompt = f"""
Convert this natural language query to valid JIRA JQL.

Query: "{query}"

Rules:
- Use correct JQL syntax
- Open tasks = status NOT IN (Done, Closed, Resolved)
- Search text via summary ~ "text" OR description ~ "text"
- Always end with ORDER BY updated DESC

Respond in JSON:
{{
  "jql": "JQL query string"
}}
"""

        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are a JIRA JQL expert."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            result = extract_json_from_response(
                response.choices[0].message.content
            )
            jql = result.get("jql") if result else None

            if jql:
                logger.info(f"Generated JQL: {jql}")
                return jql

        except Exception as e:
            logger.warning(f"LLM JQL generation failed: {e}")

        return self._build_jql_fallback(query)

    def _build_jql_fallback(self, query: str) -> str:
        q = query.lower()
        if "open" in q or "pending" in q:
            return "status NOT IN (Done, Closed, Resolved) ORDER BY updated DESC"
        return f'summary ~ "{query[:50]}" ORDER BY updated DESC'

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_description(desc) -> str:
        if not desc:
            return ""
        if isinstance(desc, dict):
            try:
                return desc["content"][0]["content"][0]["text"]
            except Exception:
                return ""
        return str(desc)

    def _permission_error_result(self) -> Dict[str, Any]:
        return self.format_result(
            title="JIRA Access Error",
            content=(
                "JIRA is configured but rejected the request.\n\n"
                "Possible causes:\n"
                "- Invalid or expired API token\n"
                "- Missing Jira project permissions\n"
                "- Organization restrictions on API access\n"
            ),
            metadata={
                "type": "error",
                "source": "jira",
                "severity": "high",
            },
        )


# Global instance
jira_mcp = JiraMCP()
