# Oatmeal Farm Network — Backend

A comprehensive FastAPI backend for the Oatmeal Farm Network platform, providing REST APIs for agricultural management, marketplace operations, user authentication, and AI-powered advisory services.

## Overview

This backend powers the Oatmeal Farm Network platform with modular APIs for:

- **Authentication & User Management** — JWT-based auth, user profiles, password recovery
- **Farm Operations** — livestock management, crop/plant knowledge, produce tracking, processed foods
- **Agricultural Services** — weather data, precision agriculture, crop rotation planning
- **Marketplace** — product catalog, Stripe payments, vendor management
- **Content Management** — blogging, events, website builder, company features
- **AI Advisory System** — intelligent farm guidance via LangGraph and Google Gemini (`saige/` subdirectory)

## Project Structure

```
.
├── routers/                         # API endpoint modules (25+ routers)
│   ├── auth.py                      # JWT authentication
│   ├── businesses.py                # Business/vendor management
│   ├── livestock.py                 # Animal management & knowledge
│   ├── plant_knowledgebase.py       # Crop & plant guidance
│   ├── produce.py                   # Produce tracking
│   ├── marketplace.py               # E-commerce operations
│   ├── weather.py                   # Weather data integration
│   ├── precision_ag.py              # Precision agriculture tools
│   └── [20+ more routers]           # See routers/ directory
│
├── saige/                           # AI Agricultural Advisory System
│   ├── api.py                       # FastAPI endpoints for Saige
│   ├── graph.py                     # LangGraph workflow orchestration
│   ├── nodes.py                     # Workflow nodes (assessment, routing, advisory)
│   ├── rag.py                       # Firestore RAG/vector search
│   ├── llm.py                       # Google Gemini LLM integration
│   ├── redis_client.py              # Redis connection & pooling
│   └── README.md                    # Full Saige documentation
│
├── main.py                          # FastAPI app initialization & middleware
├── models.py                        # SQLAlchemy & Pydantic models
├── database.py                      # Azure SQL database connection
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Cloud Run deployment
├── cloudbuild.yaml                  # GCP Cloud Build pipeline
└── .env.example                     # Environment variables template
```

## Quick Start

### Prerequisites

- Python 3.11+
- Redis 7+ (for Saige features)
- Azure SQL Server (optional, for core backend features)
- Google Cloud credentials (optional, for Saige AI advisory)

### Installation

```bash
# Clone and enter directory
git clone https://github.com/Oatmeal-Farm-Network/oatmealfarmnetworkbackend.git
cd oatmealfarmnetworkbackend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials
```

### Running the Backend

```bash
# Start main API server (port 8000)
uvicorn main:app --reload --port 8000
```

**API Documentation:** Visit `http://localhost:8000/docs`

### Running Saige AI Advisory (Optional)

```bash
# From the saige/ directory
cd saige
uvicorn api:app --reload --port 8001

# Or from root, run Saige routes integrated with main API
```

See [`saige/README.md`](saige/README.md) for full Saige setup and configuration.

## API Endpoints

All endpoints require JWT authentication via `Authorization: Bearer <token>` header (except health checks).

### Core APIs

| Module | Endpoints | Purpose |
|---|---|---|
| **auth** | `/auth/register`, `/auth/login`, `/auth/verify` | User authentication & JWT management |
| **users** | `/users/{id}`, `/users/me` | User profiles & account management |
| **businesses** | `/businesses`, `/businesses/{id}` | Vendor & farm business management |
| **livestock** | `/livestock`, `/livestock/{id}` | Animal records & knowledge base |
| **produce** | `/produce`, `/produce/{id}` | Harvest & produce tracking |
| **plant_knowledgebase** | `/plant-kb/` | Crop disease & agronomy guidance |
| **weather** | `/weather/forecast` | Weather data & forecasts |
| **marketplace** | `/marketplace/products`, `/marketplace/orders` | E-commerce operations |
| **precision_ag** | `/precision-ag/` | Soil analysis, field mapping tools |
| **crop_rotation** | `/crop-rotation/plan` | Crop rotation planning |

### Health Checks

```
GET  /                  # API info & version
GET  /health            # Shallow liveness probe
GET  /ready             # Deep readiness check (all dependencies)
GET  /health/redis      # Redis connectivity (Saige feature)
GET  /health/firestore  # Firestore connectivity (Saige feature)
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (see `.env.example`):

```env
# --- Authentication ---
SECRET_KEY=your_jwt_secret_key              # HS256 secret (required)

# --- Database ---
DB_HOST=your_azure_sql_host
DB_PORT=1433
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database

# --- Saige AI Advisory (optional) ---
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash-lite
FIRESTORE_DATABASE=charlie
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0

# --- CORS ---
FRONTEND_URL=http://localhost:3000
ALLOW_ALL_ORIGINS=false

# --- Marketplace (optional) ---
STRIPE_SECRET_KEY=your_stripe_key
SENDGRID_API_KEY=your_sendgrid_key
```

See [`saige/README.md`](saige/README.md#configuration) for full Saige configuration details.

## Deployment

### Google Cloud Run

```bash
# Build and deploy
gcloud builds submit --config cloudbuild.yaml

# Manually deploy Dockerfile
gcloud run deploy oatmealfarmnetwork \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

**Production domains:**
- API: `https://oatmealfarmnewtorkbackend-802455386518.us-central1.run.app`
- Frontend: `https://www.oatmealfarmnetwork.com`

## Technologies

| Layer | Technology |
|---|---|
| API Framework | FastAPI, Uvicorn, Starlette |
| Database | Azure SQL Server (pymssql) |
| Authentication | JWT HS256 (python-jose) |
| **Saige AI** | LangGraph, Google Gemini, Firestore, Redis |
| Marketplace | Stripe, SendGrid |
| Cloud Platform | Google Cloud (Cloud Run, Firestore) |
| Task Queue | Redis (Saige checkpoints & message buffer) |
| Vector Search | Firestore vector search + text-embedding-004 |

## Key Features

### Saige AI Advisory System

The `saige/` subdirectory contains an AI-powered agricultural advisory system:

- **Multi-domain Advisory** — livestock, crops, weather, mixed queries
- **LangGraph Orchestration** — structured workflows with state management
- **RAG Integration** — Firestore vector search with domain-specific knowledge
- **Real-time Context** — live weather data, farm assessments
- **Chat History** — Firestore persistence + Redis message buffer

→ **Full documentation:** [`saige/README.md`](saige/README.md)

### Marketplace

- Product catalog with categories
- Stripe payment integration
- Vendor management & commission tracking
- Email notifications via SendGrid

### Knowledge Bases

- **Livestock** — breed recommendations, health guidelines, husbandry practices
- **Plants** — disease identification, soil management, crop rotation
- **Ingredients** — food processing knowledge, nutrition data
- **Bakasura Products** — product/service database

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest saige/test_api_flow.py -v
```

### Project Structure for Routers

Each router is a FastAPI APIRouter:

```python
from fastapi import APIRouter, Depends
from database import get_db

router = APIRouter(prefix="/my_resource", tags=["my_resource"])

@router.get("/")
def list_my_resources(db = Depends(get_db)):
    # Implementation
    pass

@router.post("/")
def create_my_resource(data: MyModel, db = Depends(get_db)):
    # Implementation
    pass
```

Then import in `main.py`:
```python
from routers import my_resource
app.include_router(my_resource.router)
```

## Security

**Never commit:**
- `.env` files (API keys, credentials)
- `credentials/` directories (service account JSONs)
- Database passwords or tokens

The `.gitignore` excludes sensitive files. Before pushing, verify:

```bash
git status  # Confirm no .env, credentials, or secrets staged
```

**Production Checklist:**
- [ ] Generate strong random `SECRET_KEY` (32+ chars)
- [ ] Set `ALLOW_ALL_ORIGINS=false` and specify `FRONTEND_URL`
- [ ] Enable `REDIS_SSL=true` for managed Redis
- [ ] Rotate API keys, JWT secrets, and service accounts regularly
- [ ] Use environment-specific `.env` files (never commit)

## Troubleshooting

| Issue | Solution |
|---|---|
| `401 Invalid or expired token` | Verify JWT in `Authorization: Bearer <token>` header |
| `500 JWT_SECRET is not configured` | Set `SECRET_KEY` in `.env` |
| Database connection fails | Check `DB_HOST`, `DB_USER`, `DB_PASSWORD` in `.env` |
| Saige endpoints 404 | Confirm Saige routers are registered in `main.py` |
| Redis connection timeout | Verify Redis is running (`redis-cli ping`), or set `REDIS_ENABLED=false` |
| Docker build fails | Ensure `requirements.txt` is up to date and Python 3.11+ |

## Support & Contributions

- **Issues:** Report bugs on [GitHub Issues](https://github.com/Oatmeal-Farm-Network/oatmealfarmnetworkbackend/issues)
- **Discussions:** Join community discussions on GitHub
- **Contributing:** See `CONTRIBUTING.md` (if available) for contribution guidelines

## License

[Add your license information here]

## Related Repositories

- **Frontend:** [oatmeal-farm-network-frontend](https://github.com/Oatmeal-Farm-Network/oatmeal-farm-network-frontend)
- **Documentation:** [oatmeal-farm-network-docs](https://github.com/Oatmeal-Farm-Network/oatmeal-farm-network-docs)
- **Saige AI:** See [`saige/README.md`](saige/README.md) for dedicated AI advisory documentation
