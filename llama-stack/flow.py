from llama_stack_client import LlamaStackClient

client = LlamaStackClient(base_url="http://localhost:8321")


def create_agent(instructions):
    agent = client.agents.create(
        agent_config={
            "model": "Qwen/Qwen3-8B",
            "instructions": instructions,
            "enable_session_persistence": True,
        }
    )
    session = client.agents.session.create(
        agent_id=agent.agent_id, session_name="chain"
    )
    return agent.agent_id, session.session_id


def chat(agent_id, session_id, message):
    response = client.agents.turn.create(
        agent_id=agent_id,
        session_id=session_id,
        messages=[{"role": "user", "content": message}],
        stream=True,
    )
    for chunk in response:
        if not chunk.event:
            continue
        payload = chunk.event.payload
        if payload.event_type == "turn_complete":
            text = payload.turn.output_message.content
            if "</think>" in text:
                text = text.split("</think>")[-1].strip()
            return text


drafter_id, drafter_session = create_agent(
    "You are a senior IT engineer. When given a problem, write a detailed troubleshooting checklist with 5 steps. Be technical and specific."
)

simplifier_id, simplifier_session = create_agent(
    "You are a tech writer. You receive technical instructions and rewrite them in plain language that a non-technical office worker can follow. Keep it friendly and clear."
)

problem = "Employee reports that Outlook keeps freezing for 30 seconds whenever they open a large email attachment."

print("=== AGENT 1 (IT Engineer) ===")
draft = chat(drafter_id, drafter_session, problem)
print(draft)

print("\n=== AGENT 2 (Tech Writer) ===")
simplified = chat(simplifier_id, simplifier_session,
    f"Rewrite these instructions for a non-technical user:\n\n{draft}")
print(simplified)
