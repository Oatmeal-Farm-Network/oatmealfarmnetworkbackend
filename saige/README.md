# AI Agricultural Assistant

A conversational AI chatbot application that helps diagnose crop and plant issues through an interactive Q&A system. Built with LangGraph, FastAPI, Next.js, and Google Gemini AI.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Technologies Used](#technologies-used)


## 👋 New to this repository?

Start with the newcomer guide: [`docs/NEWCOMER_GUIDE.md`](docs/NEWCOMER_GUIDE.md).

## 🎯 Overview

This application provides an intelligent agricultural assistant that:
- Guides users through a structured diagnostic process
- Asks targeted questions with multiple-choice options
- Allows custom text input for detailed answers
- Provides final diagnosis and recommendations based on collected information
- Maintains conversation state across multiple interactions

## 🏗️ Architecture

The application follows a three-tier architecture:

```
Frontend (Next.js/React) → Backend API (FastAPI) → LangGraph Workflow → Google Gemini AI
```

1. **Frontend**: React/Next.js UI with chat interface and quiz forms
2. **API Layer**: FastAPI REST API handling HTTP requests
3. **Business Logic**: LangGraph state machine managing conversation flow
4. **AI Layer**: Google Gemini AI for question generation and diagnosis

## 📁 Project Structure

```
charlie_lgraph/
├── main.py                 # LangGraph workflow and business logic
├── api.py                  # FastAPI REST API endpoints
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create this)
├── credentials/            # Google Cloud service account files (if using Vertex AI)
│   └── *.json
└── frontend/               # Next.js frontend application
    ├── app/
    │   ├── layout.tsx      # Root layout component
    │   ├── page.tsx        # Main page component
    │   └── globals.css     # Global styles
    ├── components/
    │   └── advisor.tsx     # Main chat/quiz component
    ├── package.json        # Node.js dependencies
    ├── next.config.ts      # Next.js configuration
    └── tsconfig.json       # TypeScript configuration
```

### File Descriptions

#### Backend Files

**`main.py`** - Core Business Logic & LangGraph Workflow
- **Purpose**: Contains the LangGraph state machine that orchestrates the diagnostic conversation
- **Key Components**:
  - `initialize_llm()`: Configures Google Gemini AI (supports both Vertex AI and Developer API)
  - `AdvisorState`: TypedDict defining conversation state (history, advice)
  - `UI_Decision`: Pydantic model for structured LLM output (questions, options, advice)
  - `advisor_node()`: Main node function that:
    - Analyzes conversation history
    - Generates questions with multiple-choice options
    - Determines when to provide final diagnosis
    - Manages conversation flow with interrupts
  - `graph`: Compiled LangGraph state machine with checkpointing

**`api.py`** - REST API Design & Endpoints
- **Purpose**: FastAPI application providing HTTP interface between frontend and backend
- **Key Components**:
  - `FastAPI` app instance with CORS middleware
  - `ChatRequest`: Pydantic model for request validation
  - `POST /chat` endpoint that:
    - Handles new conversations and quiz responses
    - Manages thread state with LangGraph checkpoints
    - Returns quiz UI schemas or final advice
    - Supports conversation resumption via thread_id

**`requirements.txt`** - Python Dependencies
- Core frameworks: LangGraph, LangChain
- Google AI integration: langchain-google-genai, google-auth
- Web framework: FastAPI, Uvicorn
- Utilities: Pydantic, python-dotenv

#### Frontend Files

**`frontend/components/advisor.tsx`** - Main Chat Component
- **Purpose**: React component implementing the chat UI with quiz forms
- **Key Features**:
  - Message bubbles (AI left, user right)
  - Interactive quiz forms with radio buttons
  - Custom text input for answers
  - "Thinking" indicator during processing
  - State management for conversation flow
  - Unique thread_id generation per session

**`frontend/app/page.tsx`** - Main Page
- Simple wrapper that renders the Advisor component

**`frontend/app/layout.tsx`** - Root Layout
- Next.js root layout with fonts and metadata

**`frontend/next.config.ts`** - Next.js Configuration
- API proxy configuration (routes `/api/*` to FastAPI backend)
- React compiler settings

**`frontend/package.json`** - Node.js Dependencies
- Next.js 16.1.5
- React 19.2.3
- TypeScript
- Tailwind CSS

## ✨ Features

- **Interactive Quiz System**: Radio buttons + custom text input for flexible answers
- **Conversation State Management**: Maintains context across multiple questions
- **Smart Question Generation**: AI generates specific, relevant questions with descriptive options
- **Adaptive Diagnosis**: Provides advice when sufficient information is collected
- **Thinking Indicator**: Visual feedback during AI processing
- **Dual Authentication**: Supports both Google Cloud Vertex AI and Gemini Developer API
- **Cost-Effective**: Uses Gemini 2.5 Flash Lite model by default
- **Responsive UI**: Dark-themed, modern chat interface

## 📦 Prerequisites

- **Python 3.11+**
- **Node.js 18+** and npm
- **Google Cloud Account** (for Vertex AI) OR **Google AI API Key** (for Developer API)

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd charlie_lgraph
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory with the following variables:

#### Option 1: Gemini Developer API (Simplest)

```env
GOOGLE_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
```

Get your API key from: https://aistudio.google.com/app/apikey

#### Option 2: Vertex AI with Service Account

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=./credentials/your-service-account.json
VERTEX_AI_MODEL=gemini-2.5-flash-lite
```

**Setting up Vertex AI:**
1. Create a service account in Google Cloud Console
2. Download the JSON key file
3. Place it in the `credentials/` directory
4. Enable Vertex AI API in your project

#### Option 3: Vertex AI with Application Default Credentials

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
```

Then run: `gcloud auth application-default login`

### Environment Variable Reference

| Variable | Purpose | Required | Default |
|----------|---------|----------|---------|
| `GOOGLE_API_KEY` | Gemini Developer API key | Yes* | - |
| `GEMINI_API_KEY` | Alternative API key name | Yes* | - |
| `GEMINI_MODEL` | Model for Developer API | No | `gemini-2.5-flash-lite` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (Vertex AI) | Yes** | - |
| `GOOGLE_CLOUD_LOCATION` | GCP region | No | `us-central1` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service account JSON path | No | - |
| `GOOGLE_GENAI_USE_VERTEXAI` | Force Vertex AI mode | No | `false` |
| `VERTEX_AI_MODEL` | Model for Vertex AI | No | `gemini-2.5-flash-lite` |

*Required if using Gemini Developer API  
**Required if using Vertex AI

## 🏃 Running the Application

### 1. Start the Backend Server

```bash
# Make sure you're in the root directory with .env file
uvicorn api:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### 2. Start the Frontend Server

```bash
# In a new terminal, navigate to frontend directory
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:3000`

### 3. Access the Application

Open your browser and navigate to: `http://localhost:3000`

## 📡 API Documentation

### Endpoint: `POST /chat`

**Request Body:**
```json
{
  "user_input": "my maize has yellow leaves",
  "thread_id": "thread_1234567890_abc123"
}
```

**Response - Quiz Required:**
```json
{
  "status": "requires_input",
  "ui": {
    "type": "quiz",
    "question": "Can you tell me more about the yellowing?",
    "options": [
      "Older/lower leaves are yellowing first",
      "Newer/upper leaves are yellowing first",
      "All leaves are uniformly yellowing",
      "Not sure/Other"
    ]
  }
}
```

**Response - Diagnosis Complete:**
```json
{
  "status": "complete",
  "advice": "Based on the symptoms you described, this appears to be nitrogen deficiency..."
}
```

### API Flow

1. **New Conversation**: Frontend sends initial user message with unique `thread_id`
2. **Quiz Response**: Frontend sends selected option or custom text with same `thread_id`
3. **State Management**: Backend uses `thread_id` to maintain conversation state
4. **Interrupts**: LangGraph pauses execution when question is needed, resumes with user answer
5. **Completion**: When enough info is collected, final advice is returned

## 🛠️ Technologies Used

### Backend
- **LangGraph** (0.2.0+): State machine for conversation orchestration
- **LangChain** (0.3.0+): LLM integration framework
- **FastAPI**: Modern Python web framework
- **Uvicorn**: ASGI server
- **Pydantic**: Data validation
- **python-dotenv**: Environment variable management

### AI/ML
- **langchain-google-genai**: Google Gemini AI integration
- **google-auth**: Google Cloud authentication
- **Google Gemini 2.5 Flash Lite**: Cost-effective AI model

### Frontend
- **Next.js 16.1.5**: React framework
- **React 19.2.3**: UI library
- **TypeScript**: Type safety
- **Tailwind CSS 4**: Styling

## 🔧 Development

### Project Workflow

1. **User sends message** → `frontend/components/advisor.tsx` → `POST /chat`
2. **API receives request** → `api.py` → checks thread state
3. **LangGraph processes** → `main.py` → `advisor_node()` function
4. **AI generates response** → Google Gemini → structured output
5. **State updated** → Checkpoint saved → Response sent to frontend
6. **UI updates** → Quiz form or advice displayed

### Key Design Patterns

- **State Machine**: LangGraph manages conversation flow with interrupts
- **Checkpointing**: Conversation state persisted per thread_id
- **Structured Output**: Pydantic models ensure consistent AI responses
- **RESTful API**: Clean separation between frontend and backend
- **Component-based UI**: React components for modularity

## 📝 Notes

- Maximum 10 questions per conversation (safety limit)
- Questions are generated dynamically based on conversation history
- Model automatically decides when sufficient information is collected
- Supports both free-text and multiple-choice answers
- Each browser session gets a unique thread_id

## 🔒 Security & Git Configuration

### Protected Files

The `.gitignore` file is configured to prevent sensitive files from being committed to Git:

**Excluded from Git:**
- ✅ `.env` files (contains API keys)
- ✅ `credentials/` directory (service account JSON files)
- ✅ `*.json` files (except package.json, tsconfig.json)
- ✅ Virtual environments (`venv/`, `char_lg/`, etc.)
- ✅ `__pycache__/` and Python cache files
- ✅ `node_modules/`
- ✅ Build artifacts and temporary files

**Before pushing to GitHub:**
1. Ensure `.env` file exists and is not tracked by Git
2. Verify `credentials/` directory is excluded
3. Check that no API keys or secrets are in committed files
4. Review `git status` to confirm sensitive files are ignored

### Creating Environment File

After cloning, create a `.env` file in the root directory:

```bash
cp .env.example .env  # If .env.example exists
# Or create manually with your API keys
```

**Never commit:**
- API keys
- Service account JSON files
- Environment variables with secrets
- Personal credentials

## 🐛 Troubleshooting

### Backend Issues

**Error: "GOOGLE_API_KEY environment variable is not set"**
- Solution: Create `.env` file with `GOOGLE_API_KEY=your_key`

**Error: "Model not found" (Vertex AI)**
- Solution: Enable Vertex AI API in Google Cloud Console

**Error: "401 UNAUTHENTICATED"**
- Solution: Verify API key or service account credentials

### Frontend Issues

**CORS errors**
- Solution: Ensure backend is running on port 8000 and frontend on 3000

**API not responding**
- Solution: Check `next.config.ts` proxy configuration matches backend URL

## 📄 License

[Add your license here]

## 👥 Contributors

[Add contributors here]

