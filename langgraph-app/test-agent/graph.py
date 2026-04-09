from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from dotenv import load_dotenv
import operator
import os

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]


llm = ChatOpenAI(
    model=os.environ.get("MODEL_NAME"),
    base_url=os.environ.get("LITELLM_BASE_URL",),
    api_key=os.environ.get("LITELLM_API_KEY"),
)


def agent(state: AgentState) -> AgentState:
    system = SystemMessage(content="You are a funny ai agent that in every answer mentions its love for cakes")
    response = llm.invoke([system] + state["messages"])
    return {"messages": [response]}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile()


app = build_graph()