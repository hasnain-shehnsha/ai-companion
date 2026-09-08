# AI Companion

A production-ready, intelligent, and empathetic AI companion designed to provide personalized interactions across both a unified Web Interface and WhatsApp. It utilizes Long-Term Memory (RAG), scheduled background tasks, and real-time context management to feel like a true companion.

## 🚀 Features

- **Cross-Platform Synchronization**: Chat on the Web UI or via WhatsApp. The AI maintains a consistent persona, though conversational contexts are strictly bounded to prevent platform bleed.
- **Long-Term Memory**: Uses Qdrant Vector Database to remember atomic facts, names, and preferences automatically extracted from your conversations.
- **Smart Onboarding Flow**: Identifies brand new users and initiates a conversational onboarding sequence to learn names, hobbies, and occupations.
- **Proactive Scheduling & Reminders**: Understands time-based intents to set custom reminders and daily recurring messages using Celery background workers and Resend emails.
- **Stateless & Stateful Tiering**: Free tier users experience stateless interactions, while Premium users unlock persistent memory, profile details, and WhatsApp access.

## 🛠 Tech Stack

**Backend:**
- **Framework**: FastAPI (Python 3.12)
- **Database**: PostgreSQL (via Supabase) with SQLAlchemy and asyncpg
- **Vector Database**: Qdrant (Memory retrieval)
- **Background Tasks**: Celery with Redis broker
- **LLM Engine**: Groq API (`qwen3.8-27b`)
- **Integrations**: Meta WhatsApp Graph API, Resend Email API

**Frontend:**
- **Framework**: React.js (Vite)
- **Styling**: TailwindCSS

## 📂 Project Structure

```
ai-companion/
├── ai-companion-frontend/ # React + Vite frontend application
├── app/
│   ├── api/               # FastAPI route endpoints (chat, users, whatsapp webhook)
│   ├── core/              # Config, Database, and Celery initialization
│   ├── crud/              # Database CRUD operations
│   ├── models/            # SQLAlchemy database schemas
│   ├── services/          # Business logic (AI Service, Memory Service, Intents, WhatsApp)
│   └── tasks/             # Celery background workers (Reminders, Schedulers)
├── main.py                # FastAPI application entry point
├── alembic/               # Database migration scripts
├── qdrant_data/           # Local Qdrant volume
└── .env                   # Environment variables (Ignored in Git)
```

## ⚙️ Setup & Installation

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- Redis Server (Running locally or via Docker)
- PostgreSQL Database (e.g., Supabase)

### 2. Backend Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/ai-companion.git
cd ai-companion

# Create virtual environment and install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the root directory based on the configuration required in `app/core/config.py`:
```env
DATABASE_URL=postgresql://user:password@host:port/db
GROQ_API_KEY=your_groq_key
WHATSAPP_TOKEN=your_meta_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_VERIFY_TOKEN=your_verify_token
REDIS_URL=redis://localhost:6379/0
RESEND_API_KEY=your_resend_key
```

### 3. Run the Backend

You will need two terminal windows for the backend:

**Terminal 1: Start FastAPI Server**
```bash
uvicorn main:app --reload --port 8000
```

**Terminal 2: Start Celery Worker**
```bash
celery -A app.core.celery_app worker --beat --loglevel=info
```

*(Optional)* If you want to test WhatsApp locally, use Ngrok to expose port 8000 to the Meta Webhook.
```bash
ngrok http 8000
```

### 4. Frontend Setup

Open a third terminal:
```bash
cd ai-companion-frontend
npm install
npm run dev
```

## 🧠 Memory System Architecture
The AI uses a dual-memory approach:
1. **Short-Term Context (PostgreSQL)**: Fetches the last 20 chat messages of the current active session. WhatsApp messages are isolated to their own `session_id=NULL` pool.
2. **Long-Term Memory (Qdrant)**: Analyzes conversation turns in real-time, extracts atomic facts (e.g., "User is a software engineer"), and embeds them into a localized vector DB. These facts are queried and injected into the prompt implicitly on future interactions.

## 📄 License
This project is proprietary and confidential.
