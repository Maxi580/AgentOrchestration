import os
from dotenv import load_dotenv
from llama_stack_client import LlamaStackClient

load_dotenv()
LLAMA_STACK_URL = os.environ["LLAMA_STACK_URL"]
MODEL = os.environ["MODEL"]
TAVILY_KEY = os.environ["TAVILY_KEY"]

client = LlamaStackClient(base_url=LLAMA_STACK_URL)


def strip_thinking(text):
    """Qwen3 emits a <think>...</think> reasoning block before its answer."""
    if "</think>" in text:
        return text.split("</think>")[-1].strip()
    return text


class Analyst:
    def __init__(self, client, model, instructions, session_name, client_tools=None):
        self._client = client
        config = {
            "model": model,
            "instructions": instructions,
            "enable_session_persistence": True,
        }
        if client_tools:
            config["client_tools"] = client_tools
        self._agent = client.agents.create(agent_config=config)
        self._session = client.agents.session.create(
            agent_id=self._agent.agent_id, session_name=session_name,
        )


    def ask(self, message):
        """Run one turn and return the agent's final text answer."""
        response = self._client.agents.turn.create(
            agent_id=self._agent.agent_id,
            session_id=self._session.session_id,
            messages=[{"role": "user", "content": message}],
            stream=True,
        )
        for chunk in response:
            if not chunk.event:
                continue
            payload = chunk.event.payload
            if payload.event_type == "turn_complete":
                return strip_thinking(payload.turn.output_message.content)
        return ""

    def ask_with_tools(self, message, dispatch):
        messages = [{"role": "user", "content": message}]
        while True:
            response = self._client.agents.turn.create(
                agent_id=self._agent.agent_id,
                session_id=self._session.session_id,
                messages=messages, stream=True,
            )
            for chunk in response:
                if not chunk.event:
                    continue
                payload = chunk.event.payload
                if payload.event_type == "turn_complete":
                    return strip_thinking(payload.turn.output_message.content)
                if payload.event_type == "turn_awaiting_input":
                    results = []
                    for tc in payload.turn.output_message.tool_calls:
                        fn = dispatch.get(tc.tool_name)
                        out = fn(**tc.arguments) if fn else f"Unknown tool {tc.tool_name}"
                        results.append({
                            "role": "tool", "call_id": tc.call_id,
                            "tool_name": tc.tool_name, "content": out,
                        })
                    messages = results
                    break
