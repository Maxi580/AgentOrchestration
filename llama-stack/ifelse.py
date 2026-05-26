from llama_stack_client import LlamaStackClient

client = LlamaStackClient(base_url="http://localhost:8321")

CATEGORIES = ["hardware", "software", "network"]

agent = client.agents.create(
    agent_config={
        "model": "Qwen/Qwen3-8B",
        "instructions": (
            "You are a strict classifier. You will be given an IT support message. "
            "Classify it into exactly one of these categories: hardware, software, network. "
            "Respond with ONLY the single category word in lowercase. "
            "No explanation, no punctuation, no other text."
        ),
        "enable_session_persistence": False,
    }
)


def classify(message):
    session = client.agents.session.create(
        agent_id=agent.agent_id, session_name="classify"
    )
    response = client.agents.turn.create(
        agent_id=agent.agent_id,
        session_id=session.session_id,
        messages=[{"role": "user", "content": message}],
        stream=True,
    )

    text = ""
    for chunk in response:
        if not chunk.event:
            continue
        payload = chunk.event.payload
        if payload.event_type == "turn_complete":
            text = payload.turn.output_message.content

    raw = text

    if "</think>" in text:
        text = text.split("</think>")[-1]

    text = text.strip().lower()

    matched = None
    for cat in CATEGORIES:
        if cat in text:
            matched = cat
            break

    return matched, raw


tests = [
    "My laptop screen flickers and then goes black randomly.",
    "Excel crashes every time I open this one spreadsheet.",
    "I can't reach the shared drive and websites won't load.",
]

for msg in tests:
    category, raw = classify(msg)

    print(f"\nMESSAGE: {msg}")
    print(f"RAW MODEL OUTPUT: {raw!r}")

    if category == "hardware":
        print(">>> Routed to: HARDWARE")
    elif category == "software":
        print(">>> Routed to: SOFTWARE")
    elif category == "network":
        print(">>> Routed to: NETWORK")
    else:
        print(">>> FAILED TO CLASSIFY (model did not return a usable category)")