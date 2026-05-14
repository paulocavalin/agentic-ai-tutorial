# RAG Explorer

Visual step-by-step demo of **Retrieval-Augmented Generation**. Ask a question and watch the full pipeline execute: query embedding → similarity search → context injection → grounded response.

## What it demonstrates

- **Chunking** — documents split into overlapping chunks at indexing time
- **Embedding** — query and chunks converted to vectors (same model, same space)
- **Similarity search** — ranked retrieval by cosine score with visible scores and threshold
- **Context injection** — top-K chunks inserted into the LLM prompt
- **Grounded response** — LLM cites document sources and refuses to invent
- **RAG vs. no-RAG toggle** — compare a grounded answer with a direct LLM response

## Setup

```bash
cd RAG
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Run

Requires Ollama running locally with two models pulled:

```bash
# Pull models (once)
ollama pull gemma4:latest
ollama pull nomic-embed-text

# Start server
uv run python server.py
```

Open `index.html` in your browser. API runs on `http://localhost:8003`.

Documents are indexed automatically on startup. Click **Re-index** to reload them.

Override models or Ollama URL:

```bash
MODEL=llama3.2:latest EMBED_MODEL=mxbai-embed-large uv run python server.py
OLLAMA_BASE_URL=http://remote-host:11434 uv run python server.py
```

## Sample questions to try

| Question | What it demonstrates |
|----------|----------------------|
| Quantos dependentes posso incluir no plano de saúde? | High-relevance retrieval, multi-chunk answer |
| Qual é a duração da licença-maternidade? | Cross-document retrieval |
| Tenho direito a auxílio home office? | Specific policy lookup |
| Qual o valor mensal do plano por dependente? | Partial answer + honest gap disclosure |
| Qual é o nome do CEO da empresa? | Not-in-base scenario |

## Architecture

**Backend (`server.py`)** — FastAPI app on port 8003.

Two in-memory stores:
- `CHUNKS` — list of indexed chunks with pre-computed numpy embeddings

Endpoints:
- `GET /health` — status, models, readiness
- `POST /index` — (re)index the built-in sample documents
- `GET /chunks` — list all indexed chunks
- `POST /query` — embed query, retrieve top-K, generate; or direct LLM if `with_rag=false`

**Retrieval** uses cosine similarity on L2-normalized vectors (numpy, no external vector DB).  
**Embeddings** use Ollama's `/api/embed` endpoint (`nomic-embed-text` by default).

> The built-in knowledge base contains HR policy documents for a fictional company.
> To index your own documents, extend `SAMPLE_DOCS` in `server.py`.
