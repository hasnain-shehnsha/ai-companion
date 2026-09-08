# AI Companion Platform - Tech Stack & Implementation Plan

Based on the requirements document, here is a detailed breakdown of the technologies, folder structure, hardest parts to develop, and the implementation plan.

## 1. Free/Cost-Effective Tech Stack
To build this robustly while keeping infrastructure costs as close to zero as possible during development and early MVP, I recommend the following stack:

*   **Backend Framework:** **Python with FastAPI**. Python is the industry standard for AI applications, and FastAPI is blazing fast, asynchronous (perfect for handling WhatsApp webhooks and LLM streaming), and easy to scale.
*   **Database (Relational + Vector):** **PostgreSQL with `pgvector`**. By using `pgvector`, we can store both standard relational data (users, chat history, settings) and vector embeddings (for long-term AI memory) in the same free-tier database (e.g., using Supabase's free tier).
*   **AI Models (LLMs):** 
    *   *The doc mentions OpenAI.* To keep it cheap, we can use `gpt-4o-mini` for basic routing and chat, which is incredibly cheap. 
    *   *Free Alternative:* We can use **Groq** (Llama 3 70B/8B) or **Gemini 1.5 Flash** for free/ultra-cheap inference during development, using a unified wrapper like `LiteLLM` to easily swap back to OpenAI for production.
*   **Background Jobs / Scheduling:** **Redis + Celery** (or `APScheduler` for a simpler MVP). Upstash provides a generous free tier for Serverless Redis, which we can use to queue reminders and daily messages.
*   **WhatsApp API:** **WhatsApp Cloud API** (Meta). It provides 1,000 free service-category conversations per month, which is perfect for our MVP.

## 2. Folder Directory Structure
Here is a clean, scalable, and modular folder structure based on Domain-Driven Design (DDD) for the FastAPI backend:

```text
ai-companion-backend/
├── app/
│   ├── api/                  # API Endpoints
│   │   ├── routes_web.py     # Endpoints for the Web UI
│   │   └── routes_whatsapp.py# WhatsApp Webhook integration
│   ├── core/                 # App config, database connections, prompt templates
│   ├── models/               # Database ORM models (Users, Messages, Reminders)
│   ├── schemas/              # Pydantic schemas for data validation
│   ├── services/             # Core Business Logic
│   │   ├── ai_service.py     # LLM calls, intent detection, model routing
│   │   ├── memory_service.py # Vector embedding and retrieval for long-term memory
│   │   ├── whatsapp_client.py# Meta API interactions (sending templates/messages)
│   │   └── scheduler.py      # Logic for timezone conversion and queueing jobs
│   └── worker/               # Background task definitions (Celery)
│       └── tasks.py          # Daily news generation, Reminder execution
├── tests/                    # Automated testing
├── .env                      # Environment variables
├── requirements.txt          # Python dependencies
└── main.py                   # FastAPI application entry point
```

## 3. The Hardest Parts to Develop
Based on the requirements, here are the three biggest technical challenges we will face:

1.  **Conversational Reminders & Timezones:** Parsing natural language to schedule a reminder (e.g., *"Remind me to call John tomorrow morning"*) is notoriously tricky. We have to detect the missing details (What time is "morning"? What is the user's timezone?), prompt the user for clarification, convert that to UTC for the database, and trigger a background worker to fire exactly on time.
2.  **WhatsApp's 24-Hour Window Rule:** Meta enforces a strict rule: if a user hasn't messaged the bot in 24 hours, the bot *cannot* send free-form text. It can only send pre-approved templates. If a reminder or daily message falls outside this 24-hour window, the backend must detect this and fall back to an approved template instead of the AI's natural response.
3.  **Context & Memory Management:** We must implement a pipeline that doesn't just pass the entire chat history to the LLM (which gets expensive fast). We have to summarize older conversations, extract key facts (like "User has a dog named Max"), store them in the Vector DB, and retrieve them dynamically when relevant.

## 4. Implementation Plan
We will follow the exact phased approach outlined in your document, as it is logically sound.

*   **Phase 1: Core Chat MVP.** Set up FastAPI, the PostgreSQL database, and basic OpenAI integration for a simple Web chat.
*   **Phase 2: WhatsApp Integration.** Connect the Meta Webhook. Map incoming WhatsApp phone numbers to platform users. Ensure chatting on Web and WhatsApp shares the exact same database history.
*   **Phase 3: Memory & Personalization.** Implement `pgvector`. Create background tasks that extract facts from the chat and save them. Inject these facts into the system prompt for Paid users.
*   **Phase 4: Reminders.** Build the LLM intent router. If the user asks for a reminder, route them to the "Scheduler Flow". Implement Redis/Celery to trigger the message back to WhatsApp.
*   **Phase 5: Daily Messages.** Create a daily cron job that fetches daily news/weather, generates a personalized message, and uses WhatsApp Templates to send them based on the user's local timezone.
*   **Phase 6: Polish & Hardening.** Implement token usage tracking, data deletion endpoints, and fallback logic for failed WhatsApp deliveries.
