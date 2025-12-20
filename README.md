Novera AI Knowledge Assistant
🎯 Overview

Novera is a production-ready Retrieval-Augmented Generation (RAG) platform built for Finance, HRMS, and internal enterprise documentation.

It delivers accurate, citation-backed, and context-aware answers using a hybrid retrieval pipeline combined with a modern chat interface.

LLM Engine: Google Gemini Flash 2.5

Architecture: Hybrid RAG (Vector + Keyword)

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

Email-based user registration & verification

Secure password hashing

JWT-based authentication

Role-based access control (Admin / User)

Protected backend APIs and frontend routes

Input & output guardrails

📄 Document Management

Upload and manage documents

Semantic chunking with overlap

Chunk-level editing and history

Metadata and document categorization

Finance / HRMS / Policy segregation

🔍 Retrieval System

Vector similarity search using pgvector

Keyword search using PostgreSQL Full-Text Search

Hybrid retrieval fusion pipeline

Optional Cohere reranking

Source attribution for every response

💬 Chat System

Multi-turn conversations

Context-aware responses

Streaming support

Citation cards per answer

Conversation analytics

Export chat history

🖥️ Admin Capabilities

User management

Role assignment

System analytics

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

State Management: Context API + Hooks

Styling: Tailwind CSS

Build Tool: Vite

Auth: Protected Routes

Infrastructure

Docker & Docker Compose

Nginx (frontend)

Render / Railway compatible

📂 Project Structure
NOVERA/
│
├── backend/
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py
│   │   │   │   ├── chat.py
│   │   │   │   ├── documents.py
│   │   │   │   ├── search.py
│   │   │   │   ├── admin.py
│   │   │   │   └── health.py
│   │   │   └── dependencies/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── services/
│   │   │   ├── auth/
│   │   │   ├── document_processing/
│   │   │   ├── retrieval/
│   │   │   └── generation/
│   │   └── main.py
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
│   │   ├── services/
│   │   └── utils/
│   ├── nginx.conf
│   ├── Dockerfile
│   └── package.json
│
├── docker-compose.yml
├── .gitignore
├── README.md
└── Running_Docs.txt

⚙️ Environment Configuration
Backend (backend/.env)
# Core
ENV=development
SECRET_KEY=replace_with_secure_secret

# Database
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/novera

# Gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Retrieval
RETRIEVAL_TOP_K=20
SIMILARITY_THRESHOLD=0.7

# Optional Reranker
COHERE_API_KEY=your_cohere_api_key


⚠️ Never commit real secrets.
.env files are intentionally excluded via .gitignore.

🚀 Local Setup
Prerequisites

Docker & Docker Compose

4GB+ RAM recommended

Steps
# Clone repository
git clone https://github.com/Git-me-Harish/Novera-AI.git
cd Novera-AI

# Setup environment
cp backend/.env.example backend/.env
# Edit backend/.env with your keys

# Start services
docker-compose up -d

# Apply database migrations
cd backend
alembic upgrade head

Access Points

Backend API: http://localhost:8000

API Docs: http://localhost:8000/api/docs

Frontend: http://localhost:5173

🧪 Testing
cd backend

# Run tests
pytest


Manual checks:

Upload documents

Verify chunking & embeddings

Test hybrid search

Validate chat citations

Verify email authentication flow

🔐 Security Highlights

Email verification enforced

JWT authentication

Secure password hashing

Input sanitization & jailbreak detection

Hallucination filtering

Role-based admin access

📦 Deployment
Development
docker-compose up -d

Production (Render / Railway)

Connect GitHub repository

Configure environment variables

Deploy backend & frontend services

Use /api/v1/health for health checks

🗺️ Roadmap
Completed ✅

Backend RAG pipeline

Gemini Flash 2.5 integration

Email authentication

Hybrid retrieval

Admin dashboard

Document editor

Frontend UI

Upcoming 🚧

Rate limiting

Audit logs

Feedback loop for retrieval quality

Multi-language document support

Advanced analytics dashboard

🤝 Contributing

Fork the repository

Create a feature branch

git checkout -b feature/your-feature


Commit changes

Push and open a Pull Request

📄 License

MIT License

✨ Final Note

Novera is built with a strong focus on accuracy, transparency, and enterprise readiness.
It is suitable for internal knowledge systems, compliance-driven domains, and scalable deployments.
