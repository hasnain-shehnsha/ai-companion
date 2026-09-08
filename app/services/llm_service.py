from groq import AsyncGroq
from app.core.config import settings

client = AsyncGroq(api_key=settings.GROQ_API_KEY)
MODEL = "qwen/qwen3.8-27b"


async def generate_chat_completion(messages: list[dict], max_tokens: int = 800) -> str:
    """Wrapper to generate a chat completion from the LLM."""
    chat_completion = await client.chat.completions.create(
        messages=messages,
        model=MODEL,
        max_tokens=max_tokens,
    )
    return chat_completion.choices[0].message.content


async def extract_atomic_facts(conversation: str) -> list[str]:
    """Extracts a list of atomic facts from a bulk conversation history."""
    prompt = f"Extract a concise list of atomic, distinct facts about the user from the following conversation. Focus on preferences, background, and specific details. Return each fact on a new line starting with a dash (-). If there are no facts to extract, return an empty string.\n\nConversation:\n{conversation}"

    response = await generate_chat_completion(
        [
            {
                "role": "system",
                "content": "You are a memory extractor. Output only bullet points.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
    )

    content = response.strip()
    facts = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            facts.append(line.lstrip("-*").strip())
    return facts


async def extract_facts_from_single_message(message: str) -> list[str]:
    """Dynamically extracts new facts from a single user message in real-time."""
    prompt = f"Does the user reveal any new personal information, preference, or fact in this message? If yes, extract it as a bullet point starting with a dash (-). Focus strictly on the user. If no, return an empty string.\n\nMessage: {message}"

    response = await generate_chat_completion(
        [
            {
                "role": "system",
                "content": "You are a memory extractor. Output only bullet points, or an empty string if no new personal facts are present.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=128,
    )

    content = response.strip()
    facts = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            facts.append(line.lstrip("-*").strip())
    return facts


async def generate_session_title(first_message: str) -> str:
    """Generates a short 2-4 word title for a session based on the first message."""
    prompt = f"Generate a very short, 2-4 word title for a chat session that starts with this message:\n\n{first_message}"

    response = await generate_chat_completion(
        [
            {
                "role": "system",
                "content": "You are a helpful assistant. Output ONLY the title, no quotes, no extra text.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=15,
    )

    return response.strip().strip('"').strip("'")
