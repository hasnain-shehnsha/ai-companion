import asyncio
import uuid
import logging
from groq import AsyncGroq, GroqError
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.usage import UsageRecord

logger = logging.getLogger(__name__)

client = AsyncGroq(api_key=settings.GROQ_API_KEY)
MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODEL = "openai/gpt-oss-120b"


def _completion_content(chat_completion) -> tuple[str, str | None]:
    choice = chat_completion.choices[0] if chat_completion.choices else None
    content = choice.message.content if choice else ""
    return content or "", getattr(choice, "finish_reason", None)


async def generate_chat_completion(
    messages: list[dict],
    max_tokens: int = 800,
    db: AsyncSession = None,
    user_id: str = None,
    request_type: str = "chat",
    channel: str = "web",
) -> str:
    """Wrapper to generate a chat completion from the LLM with fallback and usage tracking."""
    selected_model = MODEL
    chat_completion = None

    try:
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model=selected_model,
            max_tokens=max_tokens,
        )
        content, finish_reason = _completion_content(chat_completion)

        # If response was truncated due to token limit or ended abruptly mid-clause
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

            # Genuine truncation: hit token limit or ended abruptly mid-clause
            if finish_reason == "length" or (finish_reason != "stop" and is_dangling):
                logger.warning(
                    "LLM response was truncated or ended abruptly; requesting continuation",
                    extra={"model": selected_model, "user_id": user_id},
                )

                continuation_messages = messages.copy()
                continuation_messages.append({"role": "assistant", "content": content})
                continuation_messages.append(
                    {
                        "role": "user",
                        "content": "Please continue exactly where you left off. Do not repeat what you already said or acknowledge this instruction, just continue the sentence.",
                    }
                )

                chat_completion_part2 = await client.chat.completions.create(
                    messages=continuation_messages,
                    model=selected_model,
                    max_tokens=max_tokens,
                )
                content_part2, _ = _completion_content(chat_completion_part2)
                if content_part2:
                    content += " " + content_part2.strip()

        if not content or not content.strip():
            # If primary model returns empty, attempt fallback model
            selected_model = FALLBACK_MODEL
            chat_completion = await client.chat.completions.create(
                messages=messages,
                model=selected_model,
                max_tokens=max_tokens,
            )
            content, _ = _completion_content(chat_completion)
    except GroqError as e:
        logger.warning(
            "Primary LLM model failed, attempting fallback",
            extra={
                "model": selected_model,
                "user_id": user_id,
                "error": str(e),
                "status_code": getattr(e, "status_code", None),
                "error_code": getattr(getattr(e, "body", None), "get", lambda _: None)(
                    "code"
                ),
            },
        )
        try:
            selected_model = FALLBACK_MODEL
            chat_completion = await client.chat.completions.create(
                messages=messages,
                model=selected_model,
                max_tokens=max_tokens,
            )
            content, _ = _completion_content(chat_completion)
        except GroqError as fallback_err:
            logger.error(
                "Fallback LLM model also failed",
                extra={
                    "model": selected_model,
                    "user_id": user_id,
                    "error": str(fallback_err),
                    "status_code": getattr(fallback_err, "status_code", None),
                    "error_code": getattr(
                        getattr(fallback_err, "body", None), "get", lambda _: None
                    )("code"),
                },
            )
            return ""
    except Exception as e:
        logger.exception(
            "Unexpected error in generate_chat_completion", extra={"user_id": user_id}
        )
        return ""

    if not content:
        content = ""

    if chat_completion:
        usage = getattr(chat_completion, "usage", None)
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = (input_tokens + output_tokens) * 0.0000005

        async def _log_usage():
            try:
                async with AsyncSessionLocal() as bg_db:
                    record = UsageRecord(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        model=selected_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        request_type=request_type,
                        channel=channel,
                        estimated_cost=cost,
                    )
                    bg_db.add(record)
                    await bg_db.commit()
            except Exception as e:
                logger.exception(
                    "Failed to record LLM usage in background",
                    extra={"user_id": user_id},
                )

        asyncio.create_task(_log_usage())

    return content


async def extract_atomic_facts(
    conversation: str,
    db: AsyncSession = None,
    user_id: str = None,
    channel: str = "web",
) -> list[str]:
    """Extracts a list of atomic facts from a bulk conversation history."""
    prompt = f"Extract a concise list of atomic, distinct facts about the user from the following conversation. Focus on preferences, background, and specific details. Return each fact on a new line starting with a dash (-). If there are no facts to extract, return an empty string (do not output 'None' or 'N/A'). IMPORTANT: Always extract and write the facts in English, regardless of the language used in the conversation.\n\nConversation:\n{conversation}"

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
        if line.startswith("-") or line.startswith("*"):
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
    prompt = f"Does the user explicitly state or reveal any new personal information, preference, or fact in this message? Use the previous AI message for context if needed. If yes, extract it as a bullet point starting with a dash (-). Focus strictly on explicit statements made by the user. If there are no facts to extract, return an empty string (do not output 'None' or 'N/A'). IMPORTANT: Always extract and write the fact in English, regardless of the user's language.\n\nPrevious AI message: {previous_ai_message}\n\nUser Message: {message}"

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
        if line.startswith("-") or line.startswith("*"):
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
