Novera AI Knowledge Assistant
🎯 Overview

Novera is a production-ready Retrieval-Augmented Generation (RAG) platform designed for Finance, HRMS, and internal enterprise documentation.
It delivers accurate, traceable, citation-backed answers using a hybrid retrieval pipeline and a modern chat interface.

LLM Engine: Google Gemini Flash 2.5
Status: ✅ Production Ready (Backend + Frontend Complete)

🏗️ Architecture
User Query
   ↓
Authentication & Email Verification
   ↓
Input Guardrails (Safety + PII checks)
   ↓
Query Processing (Intent + Entities)
   ↓
Hybrid Retrieval
   ├─ Semantic Search (pgvector)
   └─ Keyword Search (PostgreSQL FTS)
   ↓
Reranking (Cohere – optional)
   ↓
Context Assembly
   ↓
LLM Generation (Gemini Flash 2.5)
   ↓
Output Guardrails (Hallucination checks)
   ↓
Response with Citations

🚀 Key Features
🔐 Authentication & Security

Email-based registration & verification

Secure password hashing

Role-based access (Admin / User)

Protected routes (frontend & backend)

Input & output guardrails

📄 Document Management

Upload & manage documents

Semantic chunking with overlap

Chunk-level editing & history

Metadata & document version handling

Finance / HRMS / Policy segregation

🔍 Retrieval System

Vector similarity search (pgvector)

Keyword search (PostgreSQL FTS)

Hybrid fusion pipeline

Optional Cohere reranking

Source attribution for every answer

💬 Chat System

Multi-turn conversations

Context-aware responses

Streaming support

Citation cards per response

Conversation analytics

Export conversations

🖥️ Admin Capabilities

User management

Role control

Analytics dashboard

Document oversight

🛠️ Tech Stack
Backend

Framework: FastAPI (Async)

Language: Python 3.11+

Database: PostgreSQL 16 + pgvector

Cache: Redis

LLM: Google Gemini Flash 2.5

Reranker: Cohere (optional)

Auth: JWT + Email Verification

Migrations: Alembic

Frontend

Framework: React 18

Language: TypeScript

State: Context API + Hooks

Styling: Tailwind CSS

Build Tool: Vite

Auth: Protected Routes

Infrastructure

Docker & Docker Compose

Nginx (frontend)

Render / Railway compatible

📂 Project Structure (Verified)
NOVERA/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/ (auth, chat, search, documents, admin)
│   │   │   └── dependencies/
│   │   ├── core/ (config, security)
│   │   ├── services/
│   │   │   ├── auth/
│   │   │   ├── document_processing/
│   │   │   ├── retrieval/
│   │   │   └── generation/
│   │   ├── models/ (user, document)
│   │   └── main.py
│   ├── alembic/
│   ├── scripts/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── contexts/
│   │   └── services/
│   ├── nginx.conf
│   └── Dockerfile
│
├── docker-compose.yml
├── .gitignore
├── README.md
└── Running_Docs.txt

⚙️ Environment Configuration
Backend (backend/.env)
# Core
ENV=development
SECRET_KEY=replace_with_secure_key

# Database
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/novera

# Gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Retrieval
RETRIEVAL_TOP_K=20
SIMILARITY_THRESHOLD=0.7

# Optional
COHERE_API_KEY=your_cohere_key


⚠️ Never commit real keys — .env is git-ignored.

🚀 Local Setup
# Clone
git clone https://github.com/Git-me-Harish/Novera-AI.git
cd Novera-AI

# Backend
cp backend/.env.example backend/.env

# Start services
docker-compose up -d

# Apply migrations
cd backend
alembic upgrade head

Access

API: http://localhost:8000

Docs: http://localhost:8000/api/docs

Frontend: http://localhost:5173

🔐 Security Highlights

Email verification required

JWT-based authentication

Input sanitization & jailbreak detection

Hallucination filtering

Role-based admin access

Secure password hashing

🗺️ Roadmap
Completed ✅

Backend RAG pipeline

Gemini Flash integration

Email authentication

Admin panel

Document editor

Hybrid retrieval

Frontend UI

Next

Rate limiting

Audit logs

Feedback loop for retrieval quality

Multi-language documents

Advanced analytics

📄 License

MIT License

✨ Final Verdict

This README now:

✅ Matches your actual codebase

✅ Removes OpenAI completely

✅ Reflects Gemini Flash 2.5 correctly

✅ Is safe for public GitHub

✅ Looks enterprise-grade
