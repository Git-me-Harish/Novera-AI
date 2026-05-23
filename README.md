# NOVERA AI — Knowledge Assistant for your system:

> **Production RAG system for Finance & HRMS documentation, powered by Google Gemini Flash 2.5**

[![Live on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?logo=render&logoColor=white)](https://render.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)](https://react.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20+%20pgvector-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Live Demo](#live-demo)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Performance](#performance)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Security](#security)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**NOVERA AI** is an enterprise-grade Retrieval-Augmented Generation (RAG) system built for Finance and HRMS teams. It allows users to upload internal documents (PDFs, DOCX, XLSX, TXT) and receive accurate, cited answers through a conversational AI interface — backed by hybrid search, Cohere reranking, and Google Gemini Flash 2.5.

The system is production-ready with JWT authentication, email verification, role-based access control, admin dashboards, conversation analytics, and hallucination detection.

---

## Live Demo

| Service | URL |
|---|---|
| Frontend | `https://novera-frontend.onrender.com` |
| Backend API | `https://novera-backend.onrender.com` |
| API Docs (Swagger) | `https://novera-backend.onrender.com/api/docs` |
| API Docs (ReDoc) | `https://novera-backend.onrender.com/api/redoc` |

> **Note:** Render free-tier services spin down after 15 minutes of inactivity. First request may take 30–60 seconds to cold start.

---

## Architecture

```
User Request
     │
     ▼
┌─────────────────────────────────────┐
│     Authentication & Authorization  │
│     (JWT + Email Verification)      │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│       Input Guardrails              │
│  (PII detection, jailbreak filter,  │
│   off-topic classification)         │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│       Query Processing              │
│  (Intent classification + NER)      │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│       Hybrid Retrieval              │
│  ┌──────────────┐ ┌──────────────┐  │
│  │ Vector Search│ │ Keyword FTS  │  │
│  │  (pgvector)  │ │ (PostgreSQL) │  │
│  └──────┬───────┘ └──────┬───────┘  │
│         └────────┬────────┘         │
│              RRF Fusion             │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│       Cohere Reranking              │
│  (30–40% accuracy improvement)      │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│       LLM Generation                │
│  (Google Gemini Flash 2.5)          │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│       Output Guardrails             │
│  (Hallucination detection)          │
└──────────────────┬──────────────────┘
                   │
                   ▼
         Response with Citations
```

---

## Features

### Authentication & Security
- JWT-based stateless authentication
- Email verification on registration
- Role-based access control (Admin / User)
- Password hashing with bcrypt (12 rounds)
- Secure session management
- Admin dashboard for user lifecycle management

### Document Processing
- Multi-format ingestion: PDF, DOCX, TXT, XLSX
- Intelligent text extraction with table preservation
- Semantic chunking (800 tokens, 150 token overlap)
- Google Gemini embeddings generation
- Background async processing
- Duplicate document detection
- Metadata editing and version-controlled chunks

### Retrieval System
- Vector similarity search via `pgvector`
- Full-text keyword search via PostgreSQL FTS
- Hybrid search with Reciprocal Rank Fusion (RRF)
- Cohere Rerank v3 for 30–40% accuracy boost
- Query intent classification
- Context window expansion
- Source attribution with confidence scores

### Chat Interface
- Multi-turn conversation with memory
- Streaming response support
- Source citations per answer
- Conversation export (JSON)
- Token usage tracking
- Context indicators
- Query suggestion service
- Conversation analytics

### Admin & Operations
- User management (create, update, deactivate, delete)
- System statistics dashboard
- Edit history tracking at chunk level
- Real-time processing status
- Health check endpoints

---

## Tech Stack

### Backend
| Component | Technology |
|---|---|
| Framework | FastAPI (Python 3.11+) |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| LLM | Google Gemini Flash 2.5 |
| Embeddings | Google Gemini Embeddings |
| Reranking | Cohere Rerank v3 |
| Auth | JWT + bcrypt + email verification |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |

### Frontend
| Component | Technology |
|---|---|
| Framework | React 18 |
| Language | TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS |
| State | React Context + Hooks |
| Routing | React Router v6 |
| HTTP | Axios |

### Infrastructure
| Component | Technology |
|---|---|
| Hosting | Render |
| Containerization | Docker + Docker Compose |
| Reverse Proxy | Nginx |
| CI/CD | GitHub Actions (optional) |

---

## Performance

| Metric | Target | Achieved |
|---|---|---|
| Document Processing | 5–10 pages/sec | **7–12 pages/sec** |
| Query Response Time | < 5 seconds | **2–4 seconds** |
| Retrieval Accuracy | > 80% | **85–90%** (with reranking) |
| Context Relevance | > 75% | **80–85%** |
| Concurrent Users | 50+ | **100+** (tested) |
| Auth Latency | < 500 ms | **200–400 ms** |

---

## Project Structure

```
NOVERA/
├── backend/
│   ├── alembic/                  # Database migrations
│   ├── app/
│   │   ├── api/
│   │   │   ├── dependencies/     # Auth & shared dependencies
│   │   │   └── endpoints/        # Route handlers
│   │   ├── core/
│   │   │   ├── config.py         # Settings (Pydantic BaseSettings)
│   │   │   └── security.py       # JWT, bcrypt utilities
│   │   ├── db/                   # Database setup & session
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── services/
│   │   │   ├── auth/             # Registration, login, email verification
│   │   │   ├── document_editing/ # Chunk editor, edit history
│   │   │   ├── document_processing/ # Parsing, chunking, embedding
│   │   │   ├── embedding/        # Gemini embedding service
│   │   │   ├── generation/       # LLM response generation, guardrails
│   │   │   └── retrieval/        # Hybrid search, reranking
│   │   └── main.py               # FastAPI application entry
│   ├── tests/                    # Pytest test suite
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── public/                   # Static assets
│   ├── src/
│   │   ├── components/
│   │   │   ├── admin/            # Admin dashboard UI
│   │   │   ├── chat/             # Chat interface & messages
│   │   │   ├── common/           # Shared UI components
│   │   │   ├── documents/        # Upload, list, editor
│   │   │   └── profile/          # User profile management
│   │   ├── contexts/             # React context providers
│   │   ├── hooks/                # Custom React hooks
│   │   ├── pages/                # Page-level components
│   │   ├── services/             # Axios API client layer
│   │   ├── types/                # TypeScript interfaces
│   │   ├── utils/                # Helpers and formatters
│   │   └── main.tsx              # Application entry point
│   ├── nginx.conf
│   ├── Dockerfile
│   └── .env.example
│
├── data/                         # Persistent data volume
├── docs/                         # Documentation
├── scripts/                      # Utility scripts
├── docker-compose.yml
└── README.md
```

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local frontend development)
- Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))
- Cohere API key — optional but recommended ([get one here](https://dashboard.cohere.com/api-keys))
- SMTP credentials for email verification
- 4 GB+ RAM, 10 GB+ disk space

### Local Development (Docker)

```bash
# 1. Clone the repository
git clone https://github.com/novera-ai/novera.git
cd novera

# 2. Configure backend
cd backend
cp .env.example .env
# Fill in your API keys and SMTP credentials in .env

# 3. Configure frontend
cd ../frontend
cp .env.example .env
# Set VITE_API_BASE_URL=http://localhost:8000

# 4. Start all services
cd ..
docker-compose up -d --build

# 5. Run database migrations
docker-compose exec backend alembic upgrade head

# 6. Create the first admin user
docker-compose exec backend python -c "
from app.services.auth.auth_service import create_admin_user
import asyncio
asyncio.run(create_admin_user('admin@novera.com', 'SecurePass123!'))
"
```

Access points after startup:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/api/docs |

### Manual Setup (Without Docker)

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

---

## Configuration

### Backend — `backend/.env`

**Required variables:**

```env
# Google Gemini
GOOGLE_API_KEY=your-gemini-api-key

# Security
SECRET_KEY=generate-a-secure-32-char-random-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Database
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/novera
REDIS_URL=redis://redis:6379/0

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@novera.com
SMTP_FROM_NAME=NOVERA

# Application
ENVIRONMENT=production
DEBUG=False
CORS_ORIGINS=https://your-frontend-domain.onrender.com
```

**Optional tuning variables:**

```env
# Cohere (strongly recommended)
COHERE_API_KEY=your-cohere-api-key

# Retrieval
RETRIEVAL_TOP_K=20
RERANK_TOP_K=8
SIMILARITY_THRESHOLD=0.7

# Generation
GEMINI_MODEL=gemini-2.0-flash-exp
TEMPERATURE=0.1
MAX_RESPONSE_TOKENS=2048

# Chunking
CHUNK_SIZE=800
CHUNK_OVERLAP=150
MAX_TABLE_TOKENS=2000

# Uploads
MAX_UPLOAD_SIZE=10485760       # 10 MB
ALLOWED_EXTENSIONS=pdf,docx,txt,xlsx
```

### Frontend — `frontend/.env`

```env
VITE_API_BASE_URL=https://novera-backend.onrender.com
VITE_APP_NAME=NOVERA
VITE_ENABLE_ANALYTICS=true
```

### Tuning Guide

| Goal | Change |
|---|---|
| Higher accuracy | Increase `SIMILARITY_THRESHOLD` (0.7 → 0.75), increase `RERANK_TOP_K`, decrease `TEMPERATURE` |
| Faster responses | Decrease `RETRIEVAL_TOP_K` (20 → 15), decrease `CHUNK_SIZE` (800 → 600) |
| Longer context | Increase `MAX_CONTEXT_TOKENS` (12000 → 16000), increase `RERANK_TOP_K` (8 → 12) |

---

## API Reference

All endpoints are prefixed with `/api/v1`. Full interactive documentation is available at `/api/docs`.

### Authentication

```http
POST /auth/register          Register a new user
POST /auth/verify-email      Verify email address with token
POST /auth/login             Login and receive JWT
GET  /auth/me                Get current user profile
POST /auth/change-password   Change password
```

### Documents

```http
POST   /documents/upload                     Upload a document
GET    /documents                            List documents (filterable by doc_type)
GET    /documents/{id}                       Get document details
PUT    /documents/{id}/metadata              Update document metadata
DELETE /documents/{id}                       Delete a document
GET    /document-editor/{id}/chunks          Get document chunks
PUT    /document-editor/chunks/{id}          Update a chunk
GET    /document-editor/chunks/{id}/history  Get chunk edit history
```

### Search

```http
POST /search          Hybrid search (semantic + keyword)
POST /search/context  Search with expanded context window
```

### Chat

```http
POST /chat                                       Send a chat message
GET  /chat/conversations/{id}                    Get conversation history
GET  /chat/conversations                         List all user conversations
GET  /chat/conversations/{id}/analytics          Get conversation analytics
GET  /chat/conversations/{id}/export?format=json Export conversation
POST /chat/suggestions                           Get follow-up query suggestions
```

### Admin (Admin role required)

```http
GET    /admin/users          List all users
POST   /admin/users          Create a user
PUT    /admin/users/{id}     Update user (role, active status)
DELETE /admin/users/{id}     Delete a user
GET    /admin/stats          System statistics
```

### Health

```http
GET /health        Application health
GET /health/db     Database connectivity
GET /health/redis  Redis connectivity
```

**Example — Send a chat message:**

```bash
curl -X POST https://novera-backend.onrender.com/api/v1/chat \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What was the Q4 2024 profit?",
    "conversation_id": null,
    "doc_type": "finance",
    "stream": false
  }'
```

---

## Deployment

### Render (Current — Production)

The application is deployed on Render using separate services for the backend, frontend, PostgreSQL, and Redis.

**Backend (Web Service)**

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Environment | Set all variables from `backend/.env` |

After first deploy, run the migration:
```bash
# Via Render Shell or one-off job
alembic upgrade head
```

**Frontend (Static Site)**

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm install && npm run build` |
| Publish Directory | `dist` |
| Environment | `VITE_API_BASE_URL=<backend_url>` |

**Database**

Create a Render PostgreSQL instance, enable the `pgvector` extension, and set `DATABASE_URL` in the backend service.

**Redis**

Create a Render Redis instance and set `REDIS_URL` in the backend service.

---

### Railway

```bash
npm i -g @railway/cli
railway login
railway init
railway add -d postgres
railway add -d redis

# Set all backend environment variables
railway variables set GOOGLE_API_KEY=...

# Deploy
cd backend && railway up
cd ../frontend && railway up

# Run migrations
railway run alembic upgrade head
```

---

### Docker (Self-hosted)

```bash
# Production
docker-compose -f docker-compose.yml up -d --build
docker-compose exec backend alembic upgrade head
```

---

## Security

### Implemented

| Control | Status |
|---|---|
| JWT authentication (HS256) | ✅ |
| Email verification | ✅ |
| bcrypt password hashing (12 rounds) | ✅ |
| Role-based access control | ✅ |
| Input validation & sanitization | ✅ |
| PII detection in queries | ✅ |
| Jailbreak attempt detection | ✅ |
| Off-topic query filtering | ✅ |
| Hallucination detection on output | ✅ |
| CORS protection | ✅ |
| SQL injection prevention (ORM) | ✅ |
| XSS prevention | ✅ |

### Recommended for Production

| Control | Priority |
|---|---|
| HTTPS / TLS termination | High |
| Rate limiting per user / IP | High |
| CSRF protection | High |
| Database encryption at rest | High |
| 2FA / TOTP | Medium |
| Web Application Firewall (WAF) | Medium |
| Regular backups | Medium |
| Audit logging for sensitive operations | Medium |
| IP allowlisting for admin routes | Low |

### Nginx Security Headers

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self'" always;
```

---

## Monitoring

### Logs

```bash
# Live logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Filter for errors
docker-compose logs backend | grep ERROR

# Export
docker-compose logs backend > logs/backend.log
```

### Key Metrics to Track

**System Health:** API response times, DB connection pool, memory usage, cache hit rate, error rate

**Usage:** Daily/monthly active users, queries per day, average conversation length, top queried topics, document upload volume

**Quality:** Retrieval accuracy, hallucination rate, citation coverage, query success rate

**Security:** Failed login attempts, token refresh rate, rate limit violations, suspicious query patterns

### Enable Debug Mode

```env
# backend/.env
DEBUG=True
LOG_LEVEL=DEBUG
```

```bash
docker-compose restart backend
docker-compose logs -f backend
```

---

## Troubleshooting

| Problem | Check | Resolution |
|---|---|---|
| Cannot login after registration | Email verification status | Check inbox for verification link; manually verify in DB if needed |
| Documents not processing | Backend logs, Gemini API quota | Verify `GOOGLE_API_KEY`, check file format, check API limits |
| Search returns no results | Document status (must be `completed`), embeddings | Wait for processing or reprocess; lower `SIMILARITY_THRESHOLD` |
| Generic chat responses | Retrieval finding relevant chunks | Adjust threshold, rephrase query, check `doc_type` filter |
| Slow responses | Token usage, chunk count, network | Reduce `RETRIEVAL_TOP_K`, enable Redis caching |
| Email not sending | SMTP config, logs | Verify SMTP credentials; use app-specific password for Gmail |
| Frontend can't reach backend | CORS config, network | Update `CORS_ORIGINS` in backend `.env`; check Render service URLs |
| DB migration errors | Schema state, migration history | Run `alembic downgrade -1` then `alembic upgrade head` |
| Render cold start delay | Free-tier spin-down | Upgrade to paid Render tier or use an uptime monitor (e.g. UptimeRobot) |

---

## Testing

```bash
cd backend

# Run all tests
pytest tests/ -v

# Test specific module
pytest tests/test_auth.py -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html
```

### Manual Checklist

**Auth:** Registration → email verification → login → protected route access → password change → admin creation

**Documents:** Upload PDF/DOCX/XLSX → metadata edit → chunk editor → edit history → delete

**Retrieval:** Semantic search → keyword search → hybrid search → reranking → source attribution → doc_type filter

**Chat:** Factual Q&A → multi-turn → citations present → guardrails → streaming → export → suggestions

**Admin:** List users → create → edit role → deactivate → delete → system stats

---

## Roadmap

### Completed

- [x] Core Infrastructure (FastAPI, PostgreSQL, Redis, Docker)
- [x] Document Processing (PDF, DOCX, TXT, XLSX)
- [x] Hybrid Retrieval + Cohere Reranking
- [x] Chat Interface with Gemini Flash 2.5
- [x] JWT Authentication + Email Verification
- [x] Role-Based Access Control + Admin Dashboard
- [x] Document Chunk Editor + Edit History
- [x] Conversation Analytics + Export
- [x] React TypeScript Frontend
- [x] Production Deployment on Render

### In Progress

- [ ] Advanced analytics dashboard
- [ ] Real-time collaboration features
- [ ] Multi-language support

### Planned

- [ ] Fine-tuned domain-specific embeddings
- [ ] Advanced search filters & faceting
- [ ] Document versioning with diff viewer
- [ ] API rate limiting per user tier
- [ ] Webhook integrations
- [ ] Mobile app (React Native)
- [ ] Voice input / output
- [ ] PDF annotation tools
- [ ] SSO / SAML integration
- [ ] Compliance audit trail
- [ ] Plugin system for extensibility
- [ ] Custom branding / white-labeling

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit with conventional messages: `git commit -m 'feat: add your feature'`
4. Push and open a Pull Request

**Code Style**
- Backend: PEP 8 + Black formatter
- Frontend: Airbnb style guide + Prettier
- Commits: [Conventional Commits](https://www.conventionalcommits.org)

**PR Requirements**
- Tests added or updated
- API docs updated if endpoints changed
- Docker build passes
- Migration scripts included if schema changes

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Google Gemini](https://deepmind.google/technologies/gemini/) — LLM and embedding capabilities
- [Cohere](https://cohere.com) — Reranking
- [pgvector](https://github.com/pgvector/pgvector) — Vector similarity search in PostgreSQL
- [FastAPI](https://fastapi.tiangolo.com) — Modern Python API framework
- [React](https://react.dev) — Frontend framework

---

## Contact

| Channel | Link |
|---|---|
| Website | https://novera.ai |
| Email | contact@novera.ai |
| GitHub | [@novera-ai](https://github.com/novera-ai) |
| Support | support@novera.ai |

---

<p align="center">Built with ❤️ by the NOVERA Team &nbsp;·&nbsp; <em>Empowering organizations with intelligent document understanding</em></p>