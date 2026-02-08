"""Streamlit chat interface for enterprise search."""
import streamlit as st
import requests
import json
import os
from datetime import datetime

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page config
st.set_page_config(
    page_title="Enterprise Search",
    page_icon=None,
    layout="wide"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    import uuid
    st.session_state.thread_id = str(uuid.uuid4())
if "previous_thread_id" not in st.session_state:
    st.session_state.previous_thread_id = None

# Title
st.title("Enterprise Agentic Search")
st.caption("Intelligent search powered by LangGraph, GPT-4o, and Pinecone")

# Sidebar
with st.sidebar:
    st.header("CHAT")
    
    # Thread selection
    try:
        threads_response = requests.get(f"{BACKEND_URL}/threads", params={"limit": 100})
        if threads_response.status_code == 200:
            threads = threads_response.json()
            thread_options = {f"{t['thread_id'][:8]}... ({t['message_count']} msgs)": t['thread_id'] for t in threads}
            thread_options["New Conversation"] = None
            
            # Find current index
            current_index = 0
            if st.session_state.thread_id in thread_options.values():
                for idx, (label, tid) in enumerate(thread_options.items()):
                    if tid == st.session_state.thread_id:
                        current_index = idx
                        break
            
            selected_thread_label = st.selectbox(
                "Select Thread",
                options=list(thread_options.keys()),
                index=current_index,
                key="thread_selector"
            )
            
            selected_thread_id = thread_options[selected_thread_label]
            
            # If thread changed, load conversation history
            if selected_thread_id and selected_thread_id != st.session_state.thread_id:
                st.session_state.previous_thread_id = st.session_state.thread_id
                st.session_state.thread_id = selected_thread_id
                st.session_state.messages = []
                
                # Load conversation history
                try:
                    history_response = requests.get(f"{BACKEND_URL}/conversations/{selected_thread_id}")
                    if history_response.status_code == 200:
                        history = history_response.json()
                        # Reverse to show oldest first
                        for conv in reversed(history):
                            st.session_state.messages.append({
                                "role": "user",
                                "content": conv["query"]
                            })
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": conv["response"]
                            })
                except Exception as e:
                    st.error(f"Error loading conversation history: {str(e)}")
            
            # If "New Conversation" selected
            if selected_thread_id is None and st.session_state.previous_thread_id is not None:
                import uuid
                st.session_state.previous_thread_id = st.session_state.thread_id
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.messages = []
        else:
            st.text_input("Thread ID", value=st.session_state.thread_id, disabled=True)
            if st.button("New Conversation"):
                st.session_state.messages = []
                import uuid
                st.session_state.thread_id = str(uuid.uuid4())
                st.rerun()
    except Exception as e:
        st.text_input("Thread ID", value=st.session_state.thread_id, disabled=True)
        if st.button("New Conversation"):
            st.session_state.messages = []
            import uuid
            st.session_state.thread_id = str(uuid.uuid4())
            st.rerun()
    
    st.divider()
    
    # Show cache stats
    st.subheader("Cache Statistics")
    try:
        response = requests.get(f"{BACKEND_URL}/cache/stats")
        if response.status_code == 200:
            stats = response.json()
            
            st.metric("Redis Hit Rate", 
                     f"{stats['redis_stats'].get('keyspace_hits', 0)}")
            st.metric("PostgreSQL Queries", 
                     stats['postgres_stats'].get('total_cached_queries', 0))
    except:
        st.error("Could not fetch cache stats")
    
    st.divider()
    
    # System status
    st.subheader("System Status")
    try:
        response = requests.get(f"{BACKEND_URL}/health")
        if response.status_code == 200:
            health = response.json()
            st.success(f"Status: {health['status']}")
            st.write(f"Redis: {'OK' if health['redis_healthy'] else 'FAIL'}")
            st.write(f"PostgreSQL: {'OK' if health['postgres_healthy'] else 'FAIL'}")
            st.write(f"Pinecone: {'OK' if health['pinecone_healthy'] else 'FAIL'}")
    except:
        st.error("Backend not reachable")

# Main chat interface
st.divider()

# Create two columns: main chat on left, example queries on right
col_main, col_examples = st.columns([2, 1])

# Main chat column
with col_main:
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show metadata for assistant messages
            if message["role"] == "assistant" and "metadata" in message:
                metadata = message["metadata"]
                
                # Confidence score - inline display
                conf = metadata.get("confidence_score", {})
                if conf:
                    overall = conf.get('overall', 0)
                    semantic = conf.get('semantic_match', 0)
                    authority = conf.get('source_authority', 0)
                    recency = conf.get('recency', 0)
                    
                    # Display as inline text with styling (no background to avoid white patches)
                    st.markdown(
                        f"""
                        <div style="padding: 5px 0; margin: 5px 0;">
                            <strong>Confidence Score:</strong> 
                            Overall: <span style="color: {'#28a745' if overall >= 0.7 else '#ffc107' if overall >= 0.5 else '#dc3545'}">{overall:.2f}</span> | 
                            Semantic: {semantic:.2f} | 
                            Authority: {authority:.2f} | 
                            Recency: {recency:.2f}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                
                # Citations
                if metadata.get("citations"):
                    with st.expander("Citations"):
                        for idx, citation in enumerate(metadata["citations"], 1):
                            st.markdown(f"**[{idx}] {citation['title']}**")
                            st.caption(f"Source: {citation['source_type']} | Confidence: {citation['confidence']:.2f}")
                            st.text(citation['snippet'])
                            if citation.get('url'):
                                st.markdown(f"[View Source]({citation['url']})")
                            st.divider()
                
                # Query decomposition
                if metadata.get("decomposed_queries"):
                    with st.expander("Query Decomposition"):
                        for sub_q in metadata["decomposed_queries"]:
                            st.markdown(f"- {sub_q}")

# Chat input (at root level so it renders at bottom of page)
if prompt := st.chat_input("Ask a question about your enterprise data..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message in main column
    with col_main:
        with st.chat_message("user"):
            st.markdown(prompt)
        
            message_placeholder = st.empty()
            loading_placeholder = st.empty()
            full_response = ""
            current_step = ""
            
            try:
                # Use streaming endpoint
                with requests.post(
                    f"{BACKEND_URL}/query/stream",
                    json={
                        "query": prompt,
                        "thread_id": st.session_state.thread_id,
                        "user_id": "default_user"
                    },
                    stream=True
                ) as response:
                    metadata = {}
                    typo_message = None
                    
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            if line.startswith('data: '):
                                data = json.loads(line[6:])
                                
                                if data['type'] == 'state_update':
                                    # Show loading indicator for current step
                                    step_name = data.get('step_name', data.get('step', 'Processing'))
                                    current_step = step_name
                                    
                                    # Check for typo correction message
                                    state = data.get('state', {})
                                    if state.get('typo_correction_message') and not typo_message:
                                        typo_message = state.get('typo_correction_message')
                                        message_placeholder.info(f"Typo correction: {typo_message}")
                                    
                                    # Show loading indicator
                                    loading_placeholder.info(f"Processing: {step_name}...")
                                
                                elif data['type'] == 'answer_chunk':
                                    # Clear loading indicator when answer starts
                                    loading_placeholder.empty()
                                    full_response += data['chunk']
                                    message_placeholder.markdown(full_response + "▌")
                                
                                elif data['type'] == 'synthesis_start':
                                    step_name = data.get('step_name', 'Synthesizing final answer')
                                    loading_placeholder.info(f"Processing: {step_name}...")
                                
                                elif data['type'] == 'synthesis_complete':
                                    loading_placeholder.empty()
                                    state = data.get('state', {})
                                    metadata = {
                                        "confidence_score": state.get('confidence_details', {}),
                                        "citations": state.get('citations', []),
                                        "decomposed_queries": state.get('decomposed_queries'),
                                        "self_healing_triggered": state.get('self_healing_triggered', False),
                                        "typo_correction_message": state.get('typo_correction_message')
                                    }
                                    metadata["confidence_score"]["overall"] = state.get('confidence_score', 0.0)
                                
                                elif data['type'] == 'error':
                                    loading_placeholder.empty()
                                    st.error(f"Error: {data.get('error', 'Unknown error')}")
                                    full_response = data.get('message', 'An error occurred')
                    
                    # Clear loading indicator if still showing
                    loading_placeholder.empty()
                    message_placeholder.markdown(full_response)
                
                # Add assistant message
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "metadata": metadata
                })
                
                # Show metadata
                if metadata:
                    # Typo correction message
                    if metadata.get("typo_correction_message"):
                        st.info(f"Typo correction: {metadata['typo_correction_message']}")
                    
                    # Confidence score - inline display
                    conf = metadata.get("confidence_score", {})
                    if conf:
                        overall = conf.get('overall', 0)
                        semantic = conf.get('semantic_match', 0)
                        authority = conf.get('source_authority', 0)
                        recency = conf.get('recency', 0)
                        
                        # Display as inline text with styling (no background to avoid white patches)
                        st.markdown(
                            f"""
                            <div style="padding: 5px 0; margin: 5px 0;">
                                <strong>Confidence Score:</strong> 
                                Overall: <span style="color: {'#28a745' if overall >= 0.7 else '#ffc107' if overall >= 0.5 else '#dc3545'}">{overall:.2f}</span> | 
                                Semantic: {semantic:.2f} | 
                                Authority: {authority:.2f} | 
                                Recency: {recency:.2f}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    
                    # Citations
                    if metadata.get("citations"):
                        with st.expander("Citations"):
                            for idx, citation in enumerate(metadata["citations"], 1):
                                st.markdown(f"**[{idx}] {citation['title']}**")
                                st.caption(f"Source: {citation['source_type']} | Confidence: {citation['confidence']:.2f}")
                                st.text(citation['snippet'])
                                if citation.get('url'):
                                    st.markdown(f"[View Source]({citation['url']})")
                                st.divider()
                    
                    # Query decomposition
                    if metadata.get("decomposed_queries") and len(metadata["decomposed_queries"]) > 1:
                        with st.expander("Query Decomposition"):
                            for sub_q in metadata["decomposed_queries"]:
                                st.markdown(f"- {sub_q}")
            
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"Sorry, an error occurred: {str(e)}"
                })

# Example queries on the right side
with col_examples:
    st.header("Example Queries")
    st.divider()
    
    st.markdown("""
    **Database Queries (PostgreSQL):**
    - How many employees are in the Engineering department?
    - What is the total sales for Q4 2024?
    - Show me all products with price above $100
    
    **GitHub Queries:**
    - Show me recent GitHub issues in the main repository
    - What pull requests were merged last week?
    - Find code related to authentication in the backend
    
    **JIRA Queries:**
    - What JIRA tickets are in the current sprint?
    - Show me all bugs assigned to the engineering team
    - What epics are planned for next quarter?
    
    **Documentation (Confluence/Wiki):**
    - What is our company's vacation policy?
    - Find documentation about the API authentication system
    
    **Complex Multi-Source Queries:**
    - Compare our Q3 vs Q4 performance and explain key differences
    - What technical decisions were made regarding authentication and why?
    - Show me all discussions, tickets, and code related to the new feature launch
    """)
