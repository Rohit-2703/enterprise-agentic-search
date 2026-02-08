"""LangGraph workflow orchestrating all agents."""
from langgraph.graph import StateGraph, END
from backend.agents.state import AgentState
from backend.agents.conversation_context_node import conversation_context_node
from backend.agents.query_analysis import query_analysis_node
from backend.agents.query_decomposition import query_decomposition_node
from backend.agents.routing import routing_node
from backend.agents.retrieval import retrieval_node
from backend.agents.confidence import confidence_node, should_trigger_self_healing
from backend.agents.self_healing import self_healing_node
from backend.agents.synthesis import synthesis_node
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


def create_initial_state(
    query: str,
    thread_id: str = "default",
    user_id: str = "default_user"
) -> AgentState:
    """Create initial agent state with default values."""
    return {
        "original_query": query,
        "thread_id": thread_id,
        "user_id": user_id,
        "conversation_history": None,
        "is_follow_up": None,
        "enhanced_query": None,
        "query_intent": None,
        "extracted_entities": None,
        "is_complex": None,
        "decomposed_queries": None,
        "corrected_query": None,
        "typo_correction_message": None,
        "source_routing": None,
        "retrieved_docs": None,
        "all_retrieved_docs": None,
        "confidence_score": None,
        "confidence_details": None,
        "self_healing_triggered": False,
        "retry_count": 0,
        "reformulated_query": None,
        "final_answer": None,
        "citations": None,
        "error": None,
        "processing_steps": []
    }


def create_agent_graph():
    """Create the LangGraph agent workflow."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("conversation_context", conversation_context_node)
    workflow.add_node("query_analysis", query_analysis_node)
    workflow.add_node("query_decomposition", query_decomposition_node)
    workflow.add_node("routing", routing_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("confidence", confidence_node)
    workflow.add_node("self_healing", self_healing_node)
    workflow.add_node("synthesis", synthesis_node)
    
    workflow.set_entry_point("conversation_context")
    
    workflow.add_edge("conversation_context", "query_analysis")
    workflow.add_edge("query_analysis", "query_decomposition")
    workflow.add_edge("query_decomposition", "routing")
    workflow.add_edge("routing", "retrieval")
    workflow.add_edge("retrieval", "confidence")
    
    workflow.add_conditional_edges(
        "confidence",
        should_trigger_self_healing,
        {
            "self_healing": "self_healing",
            "synthesis": "synthesis"
        }
    )
    
    workflow.add_edge("self_healing", "confidence")
    
    workflow.add_edge("synthesis", END)
    
    app = workflow.compile()
    
    logger.info("LangGraph workflow compiled successfully")
    return app


agent_graph = create_agent_graph()


def create_streaming_graph():
    """Create a LangGraph workflow that stops before synthesis."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("conversation_context", conversation_context_node)
    workflow.add_node("query_analysis", query_analysis_node)
    workflow.add_node("query_decomposition", query_decomposition_node)
    workflow.add_node("routing", routing_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("confidence", confidence_node)
    workflow.add_node("self_healing", self_healing_node)
    
    workflow.set_entry_point("conversation_context")
    
    workflow.add_edge("conversation_context", "query_analysis")
    workflow.add_edge("query_analysis", "query_decomposition")
    workflow.add_edge("query_decomposition", "routing")
    workflow.add_edge("routing", "retrieval")
    workflow.add_edge("retrieval", "confidence")
    
    workflow.add_conditional_edges(
        "confidence",
        should_trigger_self_healing,
        {
            "self_healing": "self_healing",
            "synthesis": END
        }
    )
    
    workflow.add_edge("self_healing", "confidence")
    
    app = workflow.compile()
    
    logger.info("Streaming LangGraph workflow compiled successfully")
    return app


streaming_graph = create_streaming_graph()


def run_agent_workflow(
    query: str,
    thread_id: str = "default",
    user_id: str = "default_user"
) -> AgentState:
    """Run the complete agent workflow."""
    initial_state = create_initial_state(query, thread_id, user_id)
    
    try:
        logger.info(f"Running agent workflow for query: {query}")
        final_state = agent_graph.invoke(initial_state)
        logger.info("Agent workflow completed successfully")
        return final_state
    except Exception as e:
        logger.error(f"Agent workflow error: {e}")
        initial_state["error"] = str(e)
        initial_state["final_answer"] = "An error occurred while processing your query."
        initial_state["citations"] = []
        return initial_state


def run_agent_workflow_streaming(
    query: str,
    thread_id: str = "default",
    user_id: str = "default_user"
):
    """Run agent workflow with streaming response."""
    initial_state = create_initial_state(query, thread_id, user_id)
    
    step_names = {
        "conversation_context": "Analyzing conversation context",
        "query_analysis": "Analyzing query intent and checking for typos",
        "query_decomposition": "Decomposing complex query",
        "routing": "Routing to data sources",
        "retrieval": "Retrieving documents from sources",
        "confidence": "Calculating confidence score",
        "self_healing": "Self-healing: Reformulating query",
        "synthesis": "Synthesizing final answer"
    }
    
    try:
        logger.info(f"Running streaming workflow for query: {query}")
        
        last_state = initial_state
        reached_synthesis = False
        
        for event in streaming_graph.stream(initial_state):
            for node_name, node_state in event.items():
                last_state = node_state
                
                step_name = step_names.get(node_name, node_name.replace("_", " ").title())
                
                yield {
                    "type": "state_update",
                    "step": node_name,
                    "step_name": step_name,
                    "state": node_state
                }
        
        if should_trigger_self_healing(last_state) == "synthesis":
            reached_synthesis = True
        
        if reached_synthesis:
            from backend.agents.synthesis import SynthesisAgent
            synthesis_agent = SynthesisAgent()
            
            if last_state.get("all_retrieved_docs"):
                yield {"type": "synthesis_start", "step_name": "Synthesizing final answer", "state": last_state}
                
                try:
                    for chunk in synthesis_agent.synthesize_streaming(last_state):
                        yield {"type": "answer_chunk", "chunk": chunk}
                    
                    yield {"type": "synthesis_complete", "state": last_state}
                except Exception as synthesis_error:
                    logger.error(f"Synthesis streaming error: {synthesis_error}")
                    last_state["error"] = str(synthesis_error)
                    if not last_state.get("final_answer"):
                        last_state["final_answer"] = "An error occurred while generating the answer."
                    yield {"type": "synthesis_complete", "state": last_state}
            else:
                yield {"type": "synthesis_complete", "state": last_state}
        
        logger.info("Streaming workflow completed successfully")
        
    except Exception as e:
        logger.error(f"Streaming workflow error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        state = last_state if 'last_state' in locals() else initial_state
        state["error"] = str(e)
        if not state.get("final_answer"):
            state["final_answer"] = "An error occurred while processing your query."
        yield {
            "type": "error",
            "error": str(e),
            "message": "An error occurred while processing your query.",
            "state": state
        }
