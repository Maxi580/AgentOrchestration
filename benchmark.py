from llama_stack_client import LlamaStackClient

client = LlamaStackClient(base_url="http://localhost:8321")

# Define the tool
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

# Fake weather function (hardcoded so we know the model used it)
def get_weather(city):
    return f"Weather in {city}: 42°C, heavy snow, winds 200km/h. A perfectly normal day."


# Create agent with the client tool
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

# Chat loop that handles tool calls
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
                # Check if the model wants to call a tool
                tool_calls = turn.output_message.tool_calls
                if tool_calls:
                    for tc in tool_calls:
                        print(f"[TOOL CALL] {tc.tool_name}({tc.arguments})")
                        # Execute locally
                        result = get_weather(tc.arguments.get("city", "Unknown"))
                        print(f"[TOOL RESULT] {result}")
                        # Send result back
                        messages = [{
                            "role": "tool",
                            "call_id": tc.call_id,
                            "tool_name": tc.tool_name,
                            "content": result,
                        }]
                    break  # inner for loop, continue outer while loop
                else:
                    # No tool call, final answer
                    text = turn.output_message.content
                    if "</think>" in text:
                        text = text.split("</think>")[-1].strip()
                    return text
        else:
            continue
        continue


print(chat("What's the weather like in Berlin?"))