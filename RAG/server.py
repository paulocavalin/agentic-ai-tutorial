"""
RAG Explorer — FastAPI backend

Uses Ollama for both embeddings (nomic-embed-text) and generation (gemma4:latest).
All indexing and retrieval happens in-process with plain Python + numpy.
No external vector databases required.
"""

import json
import math
import os
import textwrap
import uuid
from typing import Any, Dict, List, Optional

import numpy as np
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
CHAT_MODEL = os.getenv("MODEL", "gemma4:latest")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
TIMEOUT = int(os.getenv("TIMEOUT", "120"))

# Similarity threshold below which we warn that the chunk may be irrelevant
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.55"))

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory vector store ──────────────────────────────────────────────────

# Each entry: {id, source, text, embedding: np.ndarray}
CHUNKS: List[Dict[str, Any]] = []

# ── Sample documents (built-in for the demo) ────────────────────────────────

SAMPLE_DOCS = [
    {
        "source": "Manual de Benefícios 2025",
        "pages": [
            (
                "p.1",
                "Bem-vindo ao Manual de Benefícios 2025. Este documento descreve todos os "
                "benefícios oferecidos pela empresa aos colaboradores e seus dependentes.",
            ),
            (
                "p.18",
                "O plano de saúde corporativo (Bradesco Saúde — Plano Empresarial Gold) cobre "
                "o colaborador titular e até 3 (três) dependentes diretos. Dependentes elegíveis: "
                "cônjuge ou companheiro(a) com união estável comprovada, filhos biológicos ou "
                "adotivos até 24 anos, e filhos com deficiência sem limite de idade. A inclusão "
                "deve ser solicitada ao RH em até 30 dias após a contratação ou ocorrência do "
                "evento (casamento, nascimento, adoção).",
            ),
            (
                "p.19",
                "Custo do plano de saúde: a empresa cobre 100% do plano do titular. Para cada "
                "dependente, o colaborador contribui com 30% do valor da mensalidade, descontado "
                "em folha de pagamento. Reajuste anual em janeiro, conforme tabela ANS. Para "
                "inclusão de dependente após o prazo de 30 dias, o colaborador aguarda o período "
                "de carência contratual.",
            ),
            (
                "p.24",
                "Vale-refeição: R$ 45,00 por dia útil trabalhado, via cartão Alelo. "
                "Vale-transporte: reembolso de até R$ 350,00 mensais mediante apresentação "
                "do comprovante de uso. Gympass: empresa cobre 60% da mensalidade dos planos "
                "Basic e Standard.",
            ),
            (
                "p.30",
                "Política de home office: colaboradores em regime híbrido têm direito a auxílio "
                "home office de R$ 150,00 mensais para cobrir custos de internet e energia. "
                "O auxílio é pago junto com a folha de setembro de cada ano, retroativo aos "
                "12 meses anteriores.",
            ),
        ],
    },
    {
        "source": "Política de Férias e Licenças",
        "pages": [
            (
                "p.1",
                "Este documento descreve as políticas de férias, licenças e afastamentos "
                "da empresa, em conformidade com a CLT e benefícios complementares.",
            ),
            (
                "p.3",
                "Férias: após 12 meses de trabalho (período aquisitivo), o colaborador tem "
                "direito a 30 dias de férias. As férias podem ser parceladas em até 3 períodos, "
                "sendo o menor deles de no mínimo 14 dias corridos. O abono pecuniário "
                "(conversão de 10 dias em dinheiro) deve ser solicitado até 15 dias antes "
                "do início das férias.",
            ),
            (
                "p.7",
                "Licença-maternidade: 180 dias (6 meses), sendo os primeiros 120 dias pagos "
                "pelo INSS e os 60 dias complementares custeados pela empresa. "
                "Licença-paternidade: 20 dias corridos a partir do nascimento ou adoção. "
                "Licença por adoção: mesmos direitos da licença-maternidade.",
            ),
            (
                "p.9",
                "Licença para estudos: colaboradores com mais de 2 anos de empresa podem "
                "solicitar licença não remunerada de até 90 dias para cursos de pós-graduação "
                "ou MBA, mantendo o vínculo empregatício. A solicitação deve ser feita com "
                "60 dias de antecedência e aprovada pelo gestor imediato e RH.",
            ),
        ],
    },
    {
        "source": "Guia de Onboarding",
        "pages": [
            (
                "p.6",
                "Benefícios ativos a partir do 1º dia de trabalho: vale-refeição, "
                "vale-transporte e plano de saúde. Para ativar o plano de saúde e incluir "
                "dependentes, acesse o portal RH (rh.empresa.com) e preencha o formulário "
                "de adesão em até 30 dias.",
            ),
            (
                "p.8",
                "Equipamentos: notebook e monitor serão entregues no primeiro dia. "
                "Para periféricos adicionais (teclado, mouse, headset), solicite via "
                "portal IT (it.empresa.com) com aprovação do gestor. Orçamento anual "
                "para periféricos: R$ 800,00 por colaborador.",
            ),
        ],
    },
]

SYSTEM_PROMPT = (
    "Você é um assistente interno de RH da empresa. Responda perguntas dos colaboradores "
    "sobre políticas, benefícios e procedimentos.\n\n"
    "REGRA FUNDAMENTAL: Responda SOMENTE com base nos documentos fornecidos no CONTEXTO abaixo.\n"
    "- Se a informação estiver no contexto: responda de forma clara e cite o documento de origem.\n"
    "- Se a informação NÃO estiver no contexto: diga explicitamente que não está disponível "
    "na base de conhecimento e sugira contato com o RH.\n"
    "- NUNCA invente políticas, valores, prazos ou benefícios que não estejam nos documentos.\n"
    "Formato de citação: 'Conforme [documento], [página]: ...'"
)

# ── Ollama helpers ──────────────────────────────────────────────────────────

def _embed(text: str) -> np.ndarray:
    resp = requests.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    vec = data.get("embeddings", [data.get("embedding", [])])
    if isinstance(vec[0], list):
        vec = vec[0]
    arr = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else arr


def _chat(messages: List[Dict]) -> str:
    resp = requests.post(
        f"{OLLAMA_BASE}/v1/chat/completions",
        json={"model": CHAT_MODEL, "messages": messages},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return str(resp.json()["choices"][0]["message"]["content"])


# ── Indexing ────────────────────────────────────────────────────────────────

def _index_documents() -> List[Dict[str, Any]]:
    events = []
    total_chunks = 0
    for doc in SAMPLE_DOCS:
        for page, text in doc["pages"]:
            chunk_id = str(uuid.uuid4())[:8]
            embedding = _embed(text)
            CHUNKS.append({
                "id": chunk_id,
                "source": doc["source"],
                "page": page,
                "text": text,
                "embedding": embedding,
            })
            total_chunks += 1
    events.append({
        "type": "index_done",
        "chunk_count": total_chunks,
        "doc_count": len(SAMPLE_DOCS),
        "docs": [d["source"] for d in SAMPLE_DOCS],
    })
    return events


# ── Retrieval ───────────────────────────────────────────────────────────────

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))  # both pre-normalized


def _retrieve(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    if not CHUNKS:
        return []
    q_vec = _embed(query)
    scored = [(c, _cosine(q_vec, c["embedding"])) for c in CHUNKS]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        {
            "id": c["id"],
            "source": c["source"],
            "page": c["page"],
            "text": c["text"],
            "score": round(score, 3),
            "relevant": score >= RELEVANCE_THRESHOLD,
        }
        for c, score in scored[:top_k]
    ]


def _build_rag_prompt(question: str, chunks: List[Dict]) -> List[Dict]:
    context_parts = []
    for ch in chunks:
        label = f"[Fonte: {ch['source']}, {ch['page']}]"
        context_parts.append(f"{label}\n{ch['text']}")
    context_text = "\n\n".join(context_parts)

    user_content = (
        f"CONTEXTO RECUPERADO:\n---\n{context_text}\n---\n\n"
        f"PERGUNTA: {question}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ── Startup indexing ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    try:
        _index_documents()
    except Exception as e:
        print(f"[WARN] Indexing failed at startup: {e}")
        print("[WARN] Call POST /index to retry.")


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "chat_model": CHAT_MODEL,
        "embed_model": EMBED_MODEL,
        "indexed_chunks": len(CHUNKS),
        "indexed_docs": len(SAMPLE_DOCS),
        "ready": len(CHUNKS) > 0,
    }


@app.post("/index")
def index_documents():
    CHUNKS.clear()
    try:
        events = _index_documents()
        return {"ok": True, "events": events, "chunk_count": len(CHUNKS)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chunks")
def list_chunks():
    return {
        "chunks": [
            {"id": c["id"], "source": c["source"], "page": c["page"], "text": c["text"]}
            for c in CHUNKS
        ],
        "count": len(CHUNKS),
    }


class QueryRequest(BaseModel):
    question: str
    top_k: int = 3
    with_rag: bool = True


@app.post("/query")
def query(req: QueryRequest):
    if not CHUNKS:
        raise HTTPException(status_code=503, detail="Index not ready. Call POST /index first.")

    events: List[Dict[str, Any]] = []

    # Step 1: embed query
    try:
        q_vec = _embed(req.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {e}")

    events.append({
        "type": "query_embedded",
        "question": req.question,
        "vector_dim": len(q_vec),
        "embed_model": EMBED_MODEL,
    })

    if not req.with_rag:
        # Baseline: ask LLM directly, no context
        try:
            raw_answer = _chat([
                {"role": "system", "content": "You are a helpful HR assistant."},
                {"role": "user", "content": req.question},
            ])
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Generation failed: {e}")
        events.append({"type": "response_no_rag", "content": raw_answer})
        return {"events": events, "answer": raw_answer, "chunks": []}

    # Step 2: retrieve
    scored = [(c, _cosine(q_vec, c["embedding"])) for c in CHUNKS]
    scored.sort(key=lambda x: x[1], reverse=True)
    top_chunks = scored[: req.top_k]

    retrieval_result = [
        {
            "id": c["id"],
            "source": c["source"],
            "page": c["page"],
            "text": c["text"],
            "score": round(score, 3),
            "relevant": score >= RELEVANCE_THRESHOLD,
        }
        for c, score in top_chunks
    ]

    events.append({
        "type": "retrieved",
        "chunks": retrieval_result,
        "threshold": RELEVANCE_THRESHOLD,
    })

    # Step 3: build prompt + generate
    messages = _build_rag_prompt(req.question, retrieval_result)
    prompt_preview = messages[1]["content"][:500] + ("…" if len(messages[1]["content"]) > 500 else "")
    events.append({"type": "prompt_built", "preview": prompt_preview, "chunk_count": len(retrieval_result)})

    try:
        answer = _chat(messages)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Generation failed: {e}")

    events.append({"type": "response", "content": answer})

    return {
        "events": events,
        "answer": answer,
        "chunks": retrieval_result,
    }
