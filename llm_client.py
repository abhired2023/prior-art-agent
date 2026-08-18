import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def call_llm(prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.2, max_tokens: int = 2048) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("Set the ANTHROPIC_API_KEY environment variable before running.")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
