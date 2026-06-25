# ⚖️ HarveySpecter

**AI-Powered Companies Act, 2013 Compliance Assistant**

Built for Chartered Accountants and Company Secretaries in India.

---

## 🚀 What It Does

Upload any legal document (PDF, image, Word, or text) and HarveySpecter will:

1. **Extract** text from your document (OCR for images, parsing for PDFs/DOCX)
2. **Analyze** it against the full Companies Act, 2013 (470 sections, 29 chapters, 7 schedules)
3. **Generate** a compliance report with exact section, page, and line references
4. **Enable** follow-up chat for deeper analysis

## 🏗️ Architecture

| Component | Technology |
|-----------|-----------|
| Frontend | Next.js 15 (App Router) + TypeScript |
| Backend | Python FastAPI |
| Database | PostgreSQL + pgvector |
| AI/LLM | Google Gemini 2.5 Flash |
| Auth | Better Auth |
| Deployment | Vercel (frontend) + Railway (backend + DB) |

## 📦 Project Structure

```
harveySpector/
├── frontend/          # Next.js 15 web application
├── backend/           # Python FastAPI service
├── docker-compose.yml # Local dev orchestration
└── .env.example       # Environment variables template
```

## 🛠️ Getting Started

### Prerequisites

- Node.js 20+
- Python 3.12+
- Docker & Docker Compose
- Gemini API key ([Get one free](https://aistudio.google.com/))

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env with your GEMINI_API_KEY
```

### 2. Start with Docker Compose

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** (with pgvector) on port 5432
- **Backend API** on port 8000
- **Frontend** on port 3000

### 3. Open the App

Visit [http://localhost:3000](http://localhost:3000)

### 4. (First time) Ingest the Companies Act

```bash
# Download the Companies Act PDF and place it in backend/data/companies_act_2013/
# Then run the ingestion script:
docker compose exec backend python -m app.knowledge_base.ingest_act
```

## 📝 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents/upload` | Upload a document |
| POST | `/api/v1/analyze` | Trigger compliance analysis |
| GET | `/api/v1/analyze/{id}` | Get analysis results |
| POST | `/api/v1/chat` | Chat with the AI |
| GET | `/health` | Health check |

## 🔑 Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `BETTER_AUTH_SECRET` | Secret for Better Auth sessions |
| `NEXT_PUBLIC_API_URL` | Backend API URL for the frontend |

## 📄 License

Private — All rights reserved.
