import pytest

from app.services.llm_service import (
    extract_atomic_facts,
    extract_facts_from_single_message,
)


@pytest.mark.asyncio
async def test_extract_atomic_facts_hallucination_prompt(mocker):
    # We want to spy on the prompt being sent to the LLM to ensure it includes hallucination prevention.
    mock_llm = mocker.patch(
        "app.services.llm_service.generate_chat_completion",
        return_value="- The user loves python",
    )

    conversation = "user: Hi, I'm just hanging out today.\nassistant: Nice to meet you! I see you love hiking."
    await extract_atomic_facts(conversation)

    mock_llm.assert_called_once()
    messages = mock_llm.call_args.args[0]
    prompt = next(m["content"] for m in messages if m["role"] == "user")

    # Assert that strict hallucination-prevention instructions are in the prompt
    assert (
        "Focus on the user's personal information, preferences, and details" in prompt
    )
    assert (
        "Do not extract facts that the assistant assumed unless the user explicitly confirmed them"
        in prompt
    )
    assert "conversation" in prompt.lower()


@pytest.mark.asyncio
async def test_extract_facts_from_single_message_hallucination_prompt(mocker):
    mock_llm = mocker.patch(
        "app.services.llm_service.generate_chat_completion",
        return_value="- The user loves python",
    )

    await extract_facts_from_single_message(
        message="What? I never said that.",
        previous_ai_message="You told me you were a professional chef!",
    )

    mock_llm.assert_called_once()
    messages = mock_llm.call_args.args[0]
    prompt = next(m["content"] for m in messages if m["role"] == "user")

    # Assert that strict hallucination-prevention instructions are in the prompt
    assert (
        "DO NOT extract any facts that the AI stated about the user unless the user explicitly confirmed them"
        in prompt
    )
    assert "Pay close attention to short answers the user gives" in prompt
