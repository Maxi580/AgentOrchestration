from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from graph import app as langgraph_app

server = FastAPI(title="LangGraph Agent")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@server.get("/health")
def health():
    return {"status": "ok"}


@server.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = langgraph_app.invoke({"messages": [HumanMessage(content=req.message)]})
    last_message = result["messages"][-1]
    return ChatResponse(response=last_message.content)