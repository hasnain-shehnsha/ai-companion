from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserTier
from app.services.memory_service import store_facts, retrieve_relevant_facts
from app.services.llm_service import (
    generate_chat_completion,
    extract_atomic_facts,
    extract_facts_from_single_message,
)
from app.crud.chat_crud import get_user_messages, save_chat_turn

SYSTEM_PROMPT = """You are a helpful, empathetic, and intelligent AI Companion. 
CRITICAL RULE 1: Never explicitly parrot the user's background, facts, or past details back to them (e.g., do NOT say "Since you are an engineer" or "Congratulations again on your car"). Use the provided context IMPLICITLY to give smart, highly-tailored, and direct answers without explaining why you know those facts.
CRITICAL RULE 2: Keep your responses CONCISE and conversational. Since you are chatting via WhatsApp and mobile interfaces, avoid writing long essays. Limit responses to 1-3 short paragraphs maximum unless the user explicitly asks for a detailed, long answer."""


async def handle_chat(
    db: AsyncSession,
    user: User | None,
    user_message: str,
    chat_history: list[dict] = None,
    session_id: str = None,
) -> dict:
    """Core orchestrator for chat: retrieves context, asks LLM, saves to DB, extracts facts concurrently."""
    current_system_prompt = SYSTEM_PROMPT

    from app.services.intent_service import analyze_intent
    from app.models.reminder import Reminder
    from dateutil.parser import parse as parse_date
    import uuid

    intent_data = await analyze_intent(user_message)
    if (
        intent_data.get("intent") == "SET_REMINDER"
        and intent_data.get("datetime_iso")
        and intent_data.get("reminder_text")
    ):
        if not user:
            return {
                "response": "Please register an account to set reminders.",
                "extracted_facts": None,
                "memory_error": None,
            }

        remind_time = parse_date(intent_data["datetime_iso"])
        reminder_text = intent_data["reminder_text"]

        if remind_time.tzinfo is None:

            remind_time = remind_time.astimezone()

        from datetime import timezone

        remind_time_utc = remind_time.astimezone(timezone.utc)

        reminder = Reminder(
            id=str(uuid.uuid4()),
            user_id=user.id,
            message=reminder_text,
            remind_at=remind_time_utc,
        )
        db.add(reminder)
        await db.commit()

        from app.tasks.reminder_tasks import send_reminder_email

        send_reminder_email.apply_async((reminder.id,), eta=remind_time_utc)

        return {
            "response": f"Got it! I'll remind you to '{reminder_text}' at {remind_time.strftime('%I:%M %p on %b %d')}.",
            "extracted_facts": None,
            "memory_error": None,
        }

    elif (
        intent_data.get("intent") == "SCHEDULE_DAILY_WHATSAPP"
        and intent_data.get("datetime_iso")
        and intent_data.get("reminder_text")
    ):
        if not user:
            return {
                "response": "Please register an account to set daily schedules.",
                "extracted_facts": None,
                "memory_error": None,
            }

        remind_time = parse_date(intent_data["datetime_iso"])
        topic = intent_data["reminder_text"]

        from app.models.subscription import DailySubscription

        if remind_time.tzinfo is None:
            remind_time = remind_time.astimezone()
        time_only = remind_time.timetz()

        subscription = DailySubscription(
            id=str(uuid.uuid4()),
            user_id=user.id,
            topic=topic,
            time_of_day=time_only,
            is_active=True,
        )
        db.add(subscription)
        await db.commit()

        return {
            "response": f"I've successfully scheduled a daily WhatsApp message for you about '{topic}' at {time_only.strftime('%I:%M %p')}.",
            "extracted_facts": None,
            "memory_error": None,
        }

    if user and user.tier == UserTier.PAID:
        current_system_prompt += (
            f"\n\nContext: You are talking to {user.first_name} {user.last_name}."
        )
        relevant_facts = await retrieve_relevant_facts(user.id, user_message)
        if relevant_facts:
            current_system_prompt += (
                f"\nHere are important facts about the user from past conversations:\n"
                + "\n".join([f"- {fact}" for fact in relevant_facts])
            )

    messages = [{"role": "system", "content": current_system_prompt}]

    if user is None or user.tier == UserTier.FREE:

        if chat_history:
            for msg in chat_history:
                messages.append(
                    {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                )
        messages.append({"role": "user", "content": user_message})

        response_text = await generate_chat_completion(messages, max_tokens=512)
        return {
            "response": response_text,
            "extracted_facts": None,
            "memory_error": None,
        }

    else:

        history = await get_user_messages(db, user.id, session_id)

        if not user.is_onboarding_completed:
            if len(history) == 0:
                messages[0][
                    "content"
                ] += "\n\n[CRITICAL INSTRUCTION: The user is brand new with zero chat history! Warmly welcome them and start onboarding by naturally asking for their name and where they are from. Keep it conversational.]"
            elif len(history) <= 6:
                messages[0][
                    "content"
                ] += "\n\n[CRITICAL INSTRUCTION: You are in the middle of onboarding a new user. Continue getting to know them by naturally asking what they do for a living or what hobbies they have. Only ask one question at a time so it doesn't feel like an interrogation.]"
            else:

                conversation_text = "\n".join(
                    [f"{msg.role}: {msg.content}" for msg in history]
                )
                new_facts = await extract_atomic_facts(conversation_text)
                if new_facts:
                    await store_facts(user.id, new_facts)
                user.is_onboarding_completed = True

                history = []

        elif len(history) > 20:

            to_summarize = history[:-20]
            history = history[-20:]

            conversation_text = "\n".join(
                [f"{msg.role}: {msg.content}" for msg in to_summarize]
            )
            new_facts = await extract_atomic_facts(conversation_text)
            if new_facts:
                await store_facts(user.id, new_facts)

        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": user_message})

        import asyncio

        ai_response_task = generate_chat_completion(messages, max_tokens=800)
        fact_extraction_task = extract_facts_from_single_message(user_message)

        ai_response, extracted_facts = await asyncio.gather(
            ai_response_task, fact_extraction_task, return_exceptions=True
        )

        if isinstance(ai_response, Exception):
            raise ai_response

        memory_error = None
        new_facts = None

        if isinstance(extracted_facts, Exception):
            memory_error = str(extracted_facts)
        elif isinstance(extracted_facts, list) and len(extracted_facts) > 0:
            new_facts = extracted_facts
            try:
                await store_facts(user.id, new_facts)
            except Exception as e:
                memory_error = str(e)

        await save_chat_turn(db, user.id, session_id, user_message, ai_response)

        return {
            "response": ai_response,
            "extracted_facts": new_facts,
            "memory_error": memory_error,
        }
