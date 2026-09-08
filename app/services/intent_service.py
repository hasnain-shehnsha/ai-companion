import json
from app.services.llm_service import client, MODEL
from datetime import datetime


async def analyze_intent(user_message: str) -> dict:
    """
    Analyzes the user's message to determine if they want to chat or set a reminder.
    Returns a dict with 'intent' ('CHAT' or 'SET_REMINDER'), and if 'SET_REMINDER',
    also 'datetime_iso' and 'reminder_text'.
    """
    now = datetime.now().astimezone()
    prompt = f"""You are an Intent Analyzer for an AI companion.
The current date and time is: {now.isoformat()}

Analyze the following user message. Determine if the user is asking to:
1. "SET_REMINDER": Remind them of something once (e.g. "remind me to buy milk").
2. "SCHEDULE_DAILY_WHATSAPP": Schedule a recurring daily message (e.g. "schedule a daily quranic ayat every morning at 8am").
3. "CHAT": Anything else, general conversation.

If it's a reminder or a schedule, extract the precise time they want it to trigger (as an ISO datetime string) and the topic/text of the reminder.
If they specify a time like '8 am', calculate it relative to the current date and time.

Respond ONLY with a raw JSON object in this format (no markdown blocks, no other text):
{{
    "intent": "SET_REMINDER" | "SCHEDULE_DAILY_WHATSAPP" | "CHAT",
    "datetime_iso": "2024-03-10T16:00:00" | null,
    "reminder_text": "Buy milk" | null
}}

User message: {user_message}"""

    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL,
        max_tokens=200,
        temperature=0.0,
    )

    content = response.choices[0].message.content.strip()

    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()

    try:
        return json.loads(content)
    except Exception:

        return {"intent": "CHAT", "datetime_iso": None, "reminder_text": None}
