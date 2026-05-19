import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("llama_stack_client").setLevel(logging.WARNING)

from llama_stack_client import LlamaStackClient

client = LlamaStackClient(base_url="http://localhost:8321")

weather_tool = {
    "name": "get_weather",
    "description": "Get the current weather for a city. Always use this when someone asks about weather.",
    "parameters": [
        {
            "name": "city",
            "parameter_type": "string",
            "description": "The city name, e.g. Berlin",
            "required": True,
        }
    ],
}


def get_weather(city):
    return f"Weather in {city}: 42°C, heavy snow, winds 200km/h. A perfectly normal day."


agent = client.agents.create(
    agent_config={
        "model": "Qwen/Qwen3-8B",
        "instructions": "You are a helpful assistant. When asked about weather, always use the get_weather tool. Report the results to the user.",
        "client_tools": [weather_tool],
        "enable_session_persistence": True,
    }
)

session = client.agents.session.create(
    agent_id=agent.agent_id, session_name="weather-test"
)


def chat(message):
    messages = [{"role": "user", "content": message}]

    while True:
        response = client.agents.turn.create(
            agent_id=agent.agent_id,
            session_id=session.session_id,
            messages=messages,
            stream=True,
        )

        for chunk in response:
            if not chunk.event:
                continue
            payload = chunk.event.payload

            if payload.event_type == "turn_complete":
                turn = payload.turn
                text = turn.output_message.content
                if "</think>" in text:
                    text = text.split("</think>")[-1].strip()
                return text

            if payload.event_type == "turn_awaiting_input":
                turn = payload.turn
                for tc in turn.output_message.tool_calls:
                    print(f"[TOOL CALL] {tc.tool_name}({tc.arguments})")
                    result = get_weather(tc.arguments.get("city", "Unknown"))
                    print(f"[TOOL RESULT] {result}")
                    messages = [{
                        "role": "tool",
                        "call_id": tc.call_id,
                        "tool_name": tc.tool_name,
                        "content": result,
                    }]
                break


print(chat("What is the weather in Berlin?"))
