import logging

from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

client = AsyncGroq(api_key=settings.GROQ_API_KEY)
MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODEL = "openai/gpt-oss-120b"


def _completion_content(chat_completion) -> tuple[str, str | None]:
    choice = chat_completion.choices[0] if chat_completion.choices else None
    content = choice.message.content if choice else ""
    return content or "", getattr(choice, "finish_reason", None)


from app.services.llm_gateway import generate_llm_response


async def generate_chat_completion(
    messages: list[dict],
    max_tokens: int = 800,
    db: AsyncSession = None,
    user_id: str = None,
    request_type: str = "chat",
    channel: str = "web",
) -> str:
    """Wrapper to generate a chat completion from the LLM with fallback and usage tracking."""
    # To determine quota limit, we fetch the user (if user_id is provided and it's a chat request)
    user_timezone = "UTC"
    quota_limit = None

    if request_type == "chat" and user_id and db:
        from sqlalchemy import select

        from app.models.user import User
        from app.services.auth_service import check_premium_entitlement

        user = (
            await db.execute(select(User).filter(User.id == user_id))
        ).scalar_one_or_none()
        if user:
            user_timezone = getattr(user, "timezone", "UTC") or "UTC"
            quota_limit = 500 if check_premium_entitlement(user) else 50

    content, finish_reason = await generate_llm_response(
        messages=messages,
        user_id=user_id,
        user_timezone=user_timezone,
        quota_limit=quota_limit,
        model=MODEL,
        channel=channel,
        request_type=request_type,
        max_tokens=max_tokens,
    )

    if request_type == "chat" and content:
        content_stripped = content.strip()
        dangling_endings = (",", "...", "…", "-", "—", ":")
        dangling_words = (
            " and",
            " or",
            " but",
            " because",
            " with",
            " the",
            " that",
            " which",
            " to",
            " of",
            " in",
            " is",
            " are",
        )
        is_dangling = content_stripped.endswith(dangling_endings) or any(
            content_stripped.lower().endswith(w) for w in dangling_words
        )

        has_punctuation = content_stripped[-1] in ".!?\"'" if content_stripped else True
        is_cut_off = is_dangling or not has_punctuation

        if finish_reason == "length" or is_cut_off:
            logger.warning(
                "LLM response was truncated or ended abruptly; requesting continuation",
                extra={"model": MODEL, "user_id": user_id},
            )

            continuation_messages = messages.copy()
            continuation_messages.append({"role": "assistant", "content": content})
            continuation_messages.append(
                {
                    "role": "user",
                    "content": "Please continue exactly where you left off. Do not repeat what you already said or acknowledge this instruction, just continue the sentence.",
                }
            )

            # Do not enforce quota limit for continuation calls
            content_part2, _ = await generate_llm_response(
                messages=continuation_messages,
                user_id=user_id,
                user_timezone=user_timezone,
                quota_limit=None,
                model=MODEL,
                channel=channel,
                request_type=request_type,
                max_tokens=max_tokens,
            )
            if content_part2:
                content += " " + content_part2.strip()

    return content


async def extract_atomic_facts(
    conversation: str,
    db: AsyncSession = None,
    user_id: str = None,
    channel: str = "web",
) -> list[str]:
    """Extracts a list of atomic facts from a bulk conversation history."""
    prompt = f"Extract a concise list of atomic, distinct facts about the user from the following conversation. Pay close attention to answers the user gives to the assistant's questions. If the assistant asks for a detail (e.g. 'Where do you live?') and the user gives a short answer (e.g. 'London'), combine them into a complete fact ('The user lives in London'). Focus on the user's personal information, preferences, and details. Do not extract facts that the assistant assumed unless the user explicitly confirmed them. Return each fact on a new line starting with a dash (-). If there are no facts to extract, return an empty string (do not output 'None' or 'N/A'). IMPORTANT: Always extract and write the facts in English, regardless of the language used in the conversation.\n\nConversation:\n{conversation}"

    response = await generate_chat_completion(
        [
            {
                "role": "system",
                "content": "You are a memory extractor. Output only bullet points.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        db=db,
        user_id=user_id,
        request_type="fact_extraction",
        channel=channel,
    )

    content = response.strip()
    facts = []
    junk_phrases = [
        "none",
        "n/a",
        "no facts",
        "no new facts",
        "no new information",
        "no facts to extract",
    ]
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*")):
            fact = line.lstrip("-*").strip()
            if fact and not any(junk in fact.lower() for junk in junk_phrases):
                facts.append(fact)
    return facts


async def extract_facts_from_single_message(
    message: str,
    previous_ai_message: str = "",
    db: AsyncSession = None,
    user_id: str = None,
    channel: str = "web",
) -> list[str]:
    """Dynamically extracts new facts from a single user message in real-time."""
    prompt = f"Does the user explicitly state or reveal any new personal information, preference, or fact in this message? Pay close attention to short answers the user gives to the previous AI message. If the AI asks for a detail (e.g. 'Where did you buy it?') and the user gives a short answer (e.g. 'London'), combine them into a complete fact ('The user bought it in London'). DO NOT extract any facts that the AI stated about the user unless the user explicitly confirmed them. If yes, extract it as a bullet point starting with a dash (-). If there are no facts to extract, return an empty string (do not output 'None' or 'N/A'). IMPORTANT: Always extract and write the fact in English, regardless of the user's language.\n\nPrevious AI message: {previous_ai_message}\n\nUser Message: {message}"

    response = await generate_chat_completion(
        [
            {
                "role": "system",
                "content": "You are a memory extractor. Output only bullet points, or an empty string if no new personal facts are present.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=128,
        db=db,
        user_id=user_id,
        request_type="fact_extraction",
        channel=channel,
    )

    content = response.strip()
    facts = []
    junk_phrases = [
        "none",
        "n/a",
        "no facts",
        "no new facts",
        "no new information",
        "no facts to extract",
    ]
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*")):
            fact = line.lstrip("-*").strip()
            if fact and not any(junk in fact.lower() for junk in junk_phrases):
                facts.append(fact)
    return facts


async def generate_session_title(
    first_message: str,
    db: AsyncSession = None,
    user_id: str = None,
    channel: str = "web",
) -> str:
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
        db=db,
        user_id=user_id,
        request_type="title_generation",
        channel=channel,
    )

    return response.strip().strip('"').strip("'")


async def generate_search_query(
    user_message: str,
    db: AsyncSession = None,
    user_id: str = None,
    channel: str = "web",
) -> str:
    """Translates and optimizes the user's message into an English search query for the vector DB."""
    prompt = f"Convert the following user message into a concise English search query to look up facts in a vector database. If it's already in English, just return the core intent. Message: '{user_message}'"

    response = await generate_chat_completion(
        [
            {
                "role": "system",
                "content": "You are a translation and search optimization assistant. Output ONLY the English search query, nothing else.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=30,
        db=db,
        user_id=user_id,
        request_type="search_query_generation",
        channel=channel,
    )

    return response.strip().strip('"').strip("'")
