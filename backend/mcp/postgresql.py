"""PostgreSQL MCP client for searching structured data using text-to-SQL conversion."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text
from backend.mcp.base import MCPClient
from backend.database.connection import engine, get_db_session
from backend.utils.config import settings
from backend.utils.logger import setup_logger
from openai import OpenAI
import json

logger = setup_logger(__name__)


class PostgreSQLMCP(MCPClient):
    """MCP client for searching structured data in PostgreSQL using text-to-SQL conversion."""
    
    def __init__(self):
        """Initialize PostgreSQL MCP and load database schema information."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.schema_info = None
        self._load_schema_info()
    
    def get_source_type(self) -> str:
        """Return the source type identifier."""
        return "postgresql"
    
    def _load_schema_info(self):
        """Load database schema information (tables and columns) for SQL generation."""
        try:
            with engine.connect() as conn:
                # Get all table names
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result]
                
                schema_info = {}
                for table in tables:
                    # Get column information
                    result = conn.execute(text(f"""
                        SELECT 
                            column_name,
                            data_type,
                            is_nullable,
                            column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public' 
                        AND table_name = '{table}'
                        ORDER BY ordinal_position
                    """))
                    
                    columns = []
                    for row in result:
                        columns.append({
                            "name": row[0],
                            "type": row[1],
                            "nullable": row[2] == "YES",
                            "default": row[3]
                        })
                    
                    schema_info[table] = {
                        "columns": columns,
                        "sample_count": self._get_table_count(conn, table)
                    }
                
                self.schema_info = schema_info
                logger.info(f"Loaded schema info for {len(tables)} tables: {list(tables)}")
                
        except Exception as e:
            logger.warning(f"Error loading schema info: {e}")
            self.schema_info = {}
    
    def _get_table_count(self, conn, table: str) -> int:
        """Get row count for a table."""
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            return result.scalar()
        except:
            return 0
    
    def _generate_sql(self, query: str) -> Optional[str]:
        """Generate SQL query from natural language using LLM with schema context."""
        if not self.schema_info:
            logger.warning("Schema info not available, cannot generate SQL")
            return None
        
        # Build schema description for LLM
        schema_description = "Database Schema:\n"
        for table_name, table_info in self.schema_info.items():
            schema_description += f"\nTable: {table_name} ({table_info['sample_count']} rows)\n"
            for col in table_info['columns']:
                schema_description += f"  - {col['name']} ({col['type']})"
                if col['nullable']:
                    schema_description += " [nullable]"
                schema_description += "\n"
        
        prompt = f"""Convert this natural language query to a safe PostgreSQL SQL query.

{schema_description}

Query: "{query}"

Rules:
1. Only use SELECT queries (no INSERT, UPDATE, DELETE, DROP, etc.)
2. Use proper table and column names from the schema above
3. Use LIMIT to restrict results (default: 10 rows)
4. Use appropriate WHERE clauses for filtering
5. Use JOINs when needed to combine related tables
6. Format dates properly
7. Handle NULL values appropriately
8. Return only valid SQL, no explanations

Respond in JSON format:
{{
  "sql": "SELECT ... FROM ... WHERE ... LIMIT 10",
  "explanation": "brief explanation of what the query does"
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a SQL expert. Generate safe, read-only PostgreSQL queries. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for precise SQL
                response_format={"type": "json_object"}
            )
            
            from backend.utils.json_parser import extract_json_from_response
            content = response.choices[0].message.content
            result = extract_json_from_response(content)
            
            if result and "sql" in result:
                sql = result["sql"].strip()
                # Remove trailing semicolon if present
                if sql.endswith(';'):
                    sql = sql[:-1]
                logger.info(f"Generated SQL: {sql}")
                return sql
            else:
                logger.error("Failed to extract SQL from LLM response")
                return None
                
        except Exception as e:
            logger.error(f"Error generating SQL: {e}")
            return None
    
    def _execute_sql(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute SQL query safely.
        
        Args:
            sql: SQL query string
        
        Returns:
            List of result rows as dictionaries
        """
        # Safety check: Only allow SELECT queries
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith('SELECT'):
            logger.error(f"Non-SELECT query rejected: {sql}")
            return []
        
        # Additional safety: Check for dangerous keywords (but allow them in string literals)
        # Split SQL into tokens to avoid false positives from column names or string values
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'TRUNCATE', 'EXEC', 'EXECUTE']
        
        # Remove string literals to avoid false positives (e.g., 'CREATE' in a string value)
        import re
        sql_without_strings = re.sub(r"'[^']*'", "''", sql_upper)
        
        # Check for dangerous keywords as whole words (not substrings)
        for keyword in dangerous_keywords:
            # Use word boundaries to match whole words only
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, sql_without_strings):
                logger.error(f"Query contains dangerous keyword '{keyword}': {sql}")
                return []
        
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                rows = []
                for row in result:
                    # Convert row to dictionary
                    row_dict = {}
                    for key, value in row._mapping.items():
                        # Convert datetime and other types to strings
                        if isinstance(value, datetime):
                            row_dict[key] = value.isoformat()
                        elif value is None:
                            row_dict[key] = None
                        else:
                            row_dict[key] = str(value)
                    rows.append(row_dict)
                
                logger.info(f"SQL query returned {len(rows)} rows")
                return rows
                
        except Exception as e:
            logger.error(f"Error executing SQL: {e}")
            return []
    
    def _format_results(self, rows: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Format SQL results as MCP search results.
        
        Args:
            rows: SQL query results
            query: Original natural language query
        
        Returns:
            List of formatted MCP results
        """
        results = []
        
        for i, row in enumerate(rows):
            # Convert row to readable text format
            content_parts = []
            for key, value in row.items():
                if value is not None:
                    content_parts.append(f"{key}: {value}")
            
            content = "\n".join(content_parts)
            title = f"Database Record {i+1}"
            
            # Create metadata
            metadata = {
                "id": f"postgresql_{hash(str(row))}",
                "timestamp": datetime.now().isoformat(),
                "author": "database",
                "url": "",
                "row_data": row,
                "query": query
            }
            
            result = self.format_result(
                content=content,
                title=title,
                metadata=metadata
            )
            results.append(result)
        
        return results
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search PostgreSQL database using text-to-SQL.
        
        Args:
            query: Natural language query
            limit: Maximum number of results
        
        Returns:
            List of matching records
        """
        try:
            # Generate SQL from natural language
            sql = self._generate_sql(query)
            
            if not sql:
                logger.warning("Could not generate SQL query")
                return []
            
            # Ensure LIMIT is set
            if "LIMIT" not in sql.upper():
                sql = f"{sql} LIMIT {limit}"
            else:
                # Replace existing LIMIT if present
                import re
                sql = re.sub(r'LIMIT\s+\d+', f'LIMIT {limit}', sql, flags=re.IGNORECASE)
            
            # Execute SQL
            rows = self._execute_sql(sql)
            
            if not rows:
                logger.info("SQL query returned no results")
                return []
            
            # Format results
            results = self._format_results(rows, query)
            
            logger.info(f"PostgreSQL search found {len(results)} results for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"PostgreSQL search error: {e}")
            return []
    
    def is_available(self) -> bool:
        """Check if PostgreSQL MCP is available."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except:
            return False


# Global PostgreSQL MCP instance
postgresql_mcp = PostgreSQLMCP()
