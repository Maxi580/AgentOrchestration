from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, SystemMessage
from typing import TypedDict, Annotated, Literal
import operator
import os


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # Fake weather for testing
    return f"The weather in {city} is 22°C and sunny."


tools = [get_weather]

llm = ChatOpenAI(
    model=os.environ.get("MODEL_NAME"),
    base_url=os.environ.get("LITELLM_BASE_URL"),
    api_key=os.environ.get("LITELLM_API_KEY"),
).bind_tools(tools)


def agent(state: AgentState) -> AgentState:
    system = SystemMessage(content="You are a helpful assistant. Use tools when needed.")
    response = llm.invoke([system] + state["messages"])
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", END]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile()


app = build_graph()