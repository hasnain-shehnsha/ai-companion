import json
from app.services.llm_service import client, MODEL
from datetime import datetime

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging

logger = logging.getLogger(__name__)

from typing import Literal, Optional
from pydantic import BaseModel, Field, ValidationError


class IntentResponse(BaseModel):
    intent: Literal["SET_REMINDER", "SCHEDULE_DAILY_WHATSAPP", "CHAT"]
    datetime_iso: Optional[datetime] = None
    reminder_text: Optional[str] = Field(
        None, min_length=1, max_length=500, strip_whitespace=True
    )
    is_general_question: bool = False
    search_query: Optional[str] = None


async def analyze_intent(
    user_message: str, user_timezone: str = "UTC"
) -> IntentResponse:
    """
    Analyzes the user's message to determine if they want to chat or set a reminder.
    Also extracts an optimized vector search query if personal memory context is relevant.
    Returns a validated IntentResponse object.
    """
    try:
        tz = ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    prompt = f"""You are an Intent Analyzer for an AI companion.
The current date and time is: {now.isoformat()}

Analyze the following user message. Determine if the user is asking to:
1. "SET_REMINDER": Remind them of something once (e.g. "remind me to buy milk").
2. "SCHEDULE_DAILY_WHATSAPP": Schedule a recurring daily message (e.g. "schedule a daily quranic ayat every morning at 8am").
3. "CHAT": Anything else, general conversation.

For CHAT messages:
- Determine whether the message is a general question unrelated to this user's personal context. Set "is_general_question" to true only for general queries like "what is photosynthesis?", "how do I cook rice?", or general calculations. Set it to false for personal questions, statements, follow-ups, greetings, opinions, or anything that could benefit from knowing this user's context. Always set it to false for reminders and schedules.
- If the user is asking about or referencing personal facts, background, past info, or details (or if recalling past context like car, job, family, preferences is helpful), generate a concise English search query in "search_query" (e.g. "user car", "user job", "birthday"). If it's a greeting, casual chit-chat, or general question where no past facts are needed, set "search_query" to null.

If it's a reminder or a schedule, extract the precise time they want it to trigger (as an ISO datetime string) and the topic/text of the reminder.
If they specify a time like '8 am', calculate it relative to the current date and time.

Respond ONLY with a raw JSON object in this format (no markdown blocks, no other text):
{{
    "intent": "SET_REMINDER" | "SCHEDULE_DAILY_WHATSAPP" | "CHAT",
    "datetime_iso": "2024-03-10T16:00:00" | null,
    "reminder_text": "Buy milk" | null,
    "is_general_question": true | false,
    "search_query": "concise english query" | null
}}

User message: {user_message}"""

    try:
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL,
            max_tokens=200,
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = (response.choices[0].message.content or "").strip()

        raw_dict = json.loads(content)
        intent_response = IntentResponse(**raw_dict)

        # Additional safe validation for future date
        if intent_response.datetime_iso is not None:
            dt = intent_response.datetime_iso
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
                intent_response.datetime_iso = dt

            if dt < now:
                from datetime import timedelta

                if intent_response.intent == "SCHEDULE_DAILY_WHATSAPP":
                    # Daily recurring schedule: if today's time already passed, advance to tomorrow
                    dt = dt + timedelta(days=1)
                    intent_response.datetime_iso = dt
                elif (now - dt).total_seconds() < 86400:
                    # User specified a time that already passed today (e.g. '8am' when it's 3pm), advance to tomorrow
                    dt = dt + timedelta(days=1)
                    intent_response.datetime_iso = dt
                else:
                    # Malformed LLM logic (genuinely past date > 1 day ago), fallback to CHAT securely
                    return IntentResponse(intent="CHAT")

        return intent_response
    except json.JSONDecodeError as e:
        logger.error(
            "Failed to parse intent JSON response",
            exc_info=True,
            extra={"error": str(e)},
        )
        return IntentResponse(intent="CHAT")
    except ValidationError as e:
        logger.error(
            "Intent response validation failed", exc_info=True, extra={"error": str(e)}
        )
        return IntentResponse(intent="CHAT")
    except Exception as e:
        logger.exception("Unexpected error in analyze_intent")
        return IntentResponse(intent="CHAT")
