# AI Companion

A production-ready, intelligent, and empathetic AI companion designed to provide personalized interactions across both a unified Web Interface and WhatsApp. It utilizes Long-Term Memory (RAG), scheduled background tasks, and real-time context management to feel like a true companion.

## 🚀 Features

- **Cross-Platform Synchronization**: Chat on the Web UI or via WhatsApp. The AI maintains a consistent persona, though conversational contexts are strictly bounded to prevent platform bleed.
- **Long-Term Memory**: Uses Qdrant Vector Database to remember atomic facts, names, and preferences automatically extracted from your conversations. Background Celery tasks use distributed Redis locking to safely summarize history without race conditions.
- **Smart Onboarding Flow**: Identifies brand new users and initiates a conversational onboarding sequence to learn names, hobbies, and occupations.
- **Proactive Scheduling & Reminders**: Understands time-based intents to set custom reminders and daily recurring messages using Celery background workers and Resend emails.
- **Stateless & Stateful Tiering**: Free tier users experience stateless interactions with strict daily LLM usage limits. Premium users unlock persistent memory, profile details, background data retention, and WhatsApp access.
- **Privacy & Safety**: Users can permanently wipe their data, which triggers a durable `DataResetJob` that safely removes all Postgres and Qdrant artifacts, retrying upon failure.

## 🛠 Tech Stack

**Backend:**
- **Framework**: FastAPI (Python 3.12)
- **Database**: PostgreSQL (via Supabase) with SQLAlchemy and asyncpg. SQLite for local testing.
- **Vector Database**: Qdrant (Memory retrieval)
- **Background Tasks**: Celery with Redis broker (handles Reminders, Webhooks, Billing, Usage Tracking, Data Wiping)
- **LLM Engine**: Groq API / OpenRouter (`qwen/qwen3.8-27b`)
- **Integrations**: Meta WhatsApp Graph API, Resend Email API
- **Testing & QA**: `pytest`, `ruff` (linter/formatter), GitHub Actions CI

**Frontend:**
- **Framework**: React.js (Vite)
- **Styling**: TailwindCSS

## 📂 Project Structure

```
ai-companion/
├── ai-companion-frontend/ # React + Vite frontend application
├── app/
│   ├── api/               # FastAPI route endpoints (chat, users, whatsapp webhook, health)
│   ├── core/              # Config, Database, and Celery initialization
│   ├── crud/              # Database CRUD operations
│   ├── models/            # SQLAlchemy database schemas
│   ├── services/          # Business logic (AI Service, Memory Service, Intents, WhatsApp)
│   └── tasks/             # Celery background workers (Reminders, Subscriptions, Webhooks, Memory)
├── tests/                 # 70+ Pytest suite (Mocks, E2E flows, DB rollbacks)
├── main.py                # FastAPI application entry point
├── alembic/               # Database migration scripts
├── pyproject.toml         # Python tool configurations (Ruff, pytest)
├── qdrant_data/           # Local Qdrant volume
└── .env                   # Environment variables (Ignored in Git)
```

## ⚙️ Setup & Installation

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- Redis Server (Running locally or via Docker)
- PostgreSQL Database
- Qdrant Server

### 2. Backend Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-companion.git
cd ai-companion

# Create virtual environment and install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt ruff pytest
```

### 3. Environment Configuration

You must create a `.env` file in the root directory. Two examples are provided:

**For Local Development:**
Copy the development template. The app will use insecure defaults (like SQLite or dev tokens) for missing variables.
```bash
cp .env.development.example .env
```
Make sure to add your `GROQ_API_KEY`.

**For Production Deployment:**
Copy the production template. The app enforces strict security and will crash on startup if ANY required secret is missing (e.g. Qdrant URL, Meta App Secret, Redis, etc).
```bash
cp .env.production.example .env
```
You must fill out ALL variables in this file before proceeding.

### 4. Database Migrations

Before starting the backend, initialize the database schema. Ensure your `DATABASE_URL` is set in your `.env`.

```bash
alembic upgrade head
```

### 5. Run the Backend

You will need two terminal windows for the backend:

**Terminal 1: Start FastAPI Server**
*For Development:*
```bash
uvicorn main:app --reload --port 8000
```
*For Production:*
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Terminal 2: Start Celery Worker**
The worker handles background tasks like reminders, webhooks, and email scheduling.
```bash
celery -A app.core.celery_app worker --beat --loglevel=info
```

*(Optional)* If you want to test WhatsApp locally, use Ngrok to expose port 8000 to the Meta Webhook.
```bash
ngrok http 8000
```

### 6. Frontend Setup

Open a third terminal:
```bash
cd ai-companion-frontend
npm install
# For local development:
npm run dev
# For production build:
npm run build
```

## 🧠 Memory System Architecture
The AI uses a dual-memory approach:
1. **Short-Term Context (PostgreSQL)**: Fetches the last 20 chat messages of the current active session. WhatsApp messages are isolated to their own `session_id=None` pool and handled distinctively. Older messages are periodically flagged and summarized in the background.
2. **Long-Term Memory (Qdrant)**: Analyzes conversation turns in real-time or via Celery background tasks, extracts atomic facts (e.g., "User is a software engineer"), and embeds them into a localized vector DB. These facts are queried and injected into the prompt implicitly on future interactions. Background summarization tasks utilize non-blocking Redis distributed locks to safely execute across multiple workers without race conditions.

## 🧪 Testing & CI

The repository contains a robust test suite covering over 75+ unique test cases:
- **Unit & Integration Tests**: Run locally via `PYTHONPATH=. pytest tests/ -v`. Tests utilize an in-memory SQLite database (`aiosqlite`) with rolled-back transactions for fast, isolated execution.
- **Mocking**: External APIs (LLMs, Resend, WhatsApp) are fully mocked to ensure reliable test execution without network calls.
- **Linting & Formatting**: Enforced via `ruff` and `black`. Check syntax with `ruff check app tests main.py`.
- **CI Pipeline**: GitHub Actions automatically run linting, tests, and a dedicated Postgres migration smoke check (`tests/test_migrations.py`) on every push to `main`.

## 📄 License
This project is proprietary and confidential.
