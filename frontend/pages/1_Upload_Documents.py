"""Document upload page for adding custom knowledge to Pinecone."""
import streamlit as st
import requests
import os

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page config
st.set_page_config(
    page_title="Upload Documents",
    page_icon=None,
    layout="wide"
)

st.title("Upload Documents to Knowledge Base")
st.caption("Add your own documents to the enterprise search system")

# Tab selection
tab1, tab2 = st.tabs(["Upload Text", "Manage Documents"])

# Tab 1: Upload Text
with tab1:
    st.header("Upload Text Content")
    
    with st.form("text_upload_form"):
        title = st.text_input("Document Title*", placeholder="e.g., Q1 2025 Product Strategy")
        
        source_type = st.selectbox(
            "Source Type",
            ["custom_upload", "policy", "strategy", "technical_doc", "meeting_notes", "other"]
        )
        
        chunking_strategy = st.selectbox(
            "Chunking Strategy",
            ["auto", "sections", "paragraphs", "semantic", "tokens"],
            help="auto: Smart detection | sections: By headings | paragraphs: By paragraphs | semantic: By sentences | tokens: Fixed size"
        )
        
        max_chunk_size = st.slider(
            "Max Chunk Size (characters)",
            500, 2000, 1000,
            help="Smaller chunks = more precise search, larger chunks = more context"
        )
        
        text_content = st.text_area(
            "Document Content*",
            height=300,
            placeholder="Paste your document content here...\n\nTip: Use markdown headings (# ## ###) for better section-based chunking"
        )
        
        submit_text = st.form_submit_button("Upload Text", type="primary", use_container_width=True)
        
        if submit_text:
            if not title or not text_content:
                st.error("Please provide both title and content")
            else:
                with st.spinner("Uploading and indexing document..."):
                    try:
                        response = requests.post(
                            f"{BACKEND_URL}/documents/upload",
                            data={
                                "title": title,
                                "text": text_content,
                                "source_type": source_type,
                                "chunking_strategy": chunking_strategy,
                                "max_chunk_size": max_chunk_size
                            }
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            st.success(f"Document uploaded successfully!")
                            
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Chunks Created", result['chunks_created'])
                            col2.metric("Chunks Indexed", result['chunks_indexed'])
                            col3.metric("Strategy Used", result['chunking_strategy'])
                            
                            st.info(f"Document ID: `{result['document_id']}`")
                        else:
                            st.error(f"Upload failed: {response.json().get('detail', 'Unknown error')}")
                    
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

# Tab 2: Manage Documents
with tab2:
    st.header("Uploaded Documents")
    
    st.markdown("""
    **Manage Documents** allows you to view and delete documents that have been uploaded to the knowledge base.
    
    - View document metadata (title, source type, author, chunk count)
    - Delete documents (removes from both Pinecone vector database and PostgreSQL)
    - Refresh the list to see the latest documents
    """)
    
    if st.button("Refresh List"):
        st.rerun()
    
    try:
        response = requests.get(f"{BACKEND_URL}/documents/list")
        
        if response.status_code == 200:
            data = response.json()
            documents = data.get("documents", [])
            total_count = data.get("total", 0)
            
            if not documents:
                st.info("No documents uploaded yet. Upload your first document above!")
            else:
                st.write(f"**Total documents:** {total_count}")
                
                for doc in documents:
                    with st.expander(f"{doc['title']} ({doc['chunk_count']} chunks)"):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.write(f"**Document ID:** `{doc['document_id']}`")
                            st.write(f"**Source Type:** {doc['source_type']}")
                            st.write(f"**Author:** {doc['author']}")
                            st.write(f"**Indexed:** {doc['indexed_at'][:19]}")
                            st.write(f"**Chunks:** {doc['chunk_count']}")
                        
                        with col2:
                            if st.button("Delete", key=f"delete_{doc['document_id']}"):
                                try:
                                    del_response = requests.delete(
                                        f"{BACKEND_URL}/documents/{doc['document_id']}"
                                    )
                                    if del_response.status_code == 200:
                                        st.success("Document deleted successfully!")
                                        st.rerun()
                                    else:
                                        error_msg = del_response.json().get('detail', 'Delete failed')
                                        st.error(f"Delete failed: {error_msg}")
                                except Exception as e:
                                    st.error(f"Error: {str(e)}")
        else:
            st.error("Failed to load documents")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")

# Sidebar info
with st.sidebar:
    st.header("About")
    
    st.markdown("""
    ### Document Upload
    
    Upload your own documents to make them searchable in the enterprise search system.
    
    **Chunking Strategies:**
    - **Auto**: Smart detection based on content
    - **Sections**: Split by headings (# ## ###)
    - **Paragraphs**: Split by paragraphs
    - **Semantic**: Split by sentences with overlap
    - **Tokens**: Fixed-size chunks
    
    **Tips:**
    - Use markdown headings for better structure
    - Optimal chunk size: 800-1200 characters
    - Smaller chunks = more precise search
    - Larger chunks = more context
    """)
    
    st.divider()
    
    st.markdown("""
    ### Example Document
    
    Try uploading a document like:
    
    ```
    # Company Policy
    
    ## Vacation Policy
    Employees get 20 days...
    
    ## Remote Work Policy
    Hybrid model with...
    ```
    """)
