# 🧠 Simulação de Fluxo Agêntico — Agente com Memória (Curto e Longo Prazo)

---

## 🗺️ Visão Geral do Sistema

**Cenário:** Um assistente pessoal de produtividade que acompanha um desenvolvedor ao longo de múltiplas sessões. Ele aprende preferências, registra decisões passadas e personaliza respostas usando o que já sabe sobre o usuário — mesmo depois que a janela de contexto é reiniciada.

O fluxo é dividido em **duas sessões** para ilustrar a diferença entre memória de curto e longo prazo:

```
══════════════════ SESSÃO 1 ══════════════════

Usuário
  │
  ▼
Modelo (LLM)
  │
  ├─► [REASONING] Identifica informações relevantes para guardar
  │
  ├─► tool: remember({type: "semantic", content: "prefere Python"})
  │       └─► salva em memória persistente
  │
  ├─► tool: remember({type: "episodic", content: "escolheu FastAPI para projeto X"})
  │       └─► salva em memória persistente
  │
  └─► Resposta + confirmação de que memorizou

══════════════════ SESSÃO 2 ══════════════════
(janela de contexto zerada — sem histórico da sessão anterior)

Usuário
  │
  ▼
Modelo (LLM)
  │
  ├─► [REASONING] Percebe que precisa de contexto sobre o usuário
  │
  ├─► tool: recall({query: "preferências de linguagem e frameworks"})
  │       └─► retorna memórias relevantes da sessão 1
  │
  ├─► [REASONING] Usa memórias para personalizar resposta
  │
  └─► Resposta personalizada com base no histórico memorizado
```

**Componentes envolvidos:**
- **Modelo:** LLM com acesso às ferramentas de memória
- **Tool `remember`:** persiste informações na memória de longo prazo (arquivo local ou banco vetorial)
- **Tool `recall`:** recupera memórias relevantes por busca semântica
- **Memória de curto prazo:** janela de contexto — mensagens da sessão atual
- **Memória de longo prazo:** armazenamento externo — sobrevive entre sessões

---

## 📐 Tipos de Memória Ilustrados

| Tipo | Onde vive | Duração | Exemplo |
|------|-----------|---------|---------|
| **Curto prazo** | Janela de contexto | Só na sessão atual | "O usuário disse X nesta conversa" |
| **Longo prazo — Episódica** | Armazenamento externo | Persiste entre sessões | "Na última sessão, o usuário escolheu FastAPI" |
| **Longo prazo — Semântica** | Armazenamento externo | Persiste entre sessões | "O usuário prefere Python e projetos com deploy rápido" |

---

## ⚙️ System Prompt

```system
Você é um assistente pessoal de produtividade para desenvolvedores.

Ferramentas de memória disponíveis:
- remember(type, content, tags): persiste uma informação importante na memória de longo prazo.
  - type: "semantic" (preferências, fatos sobre o usuário) ou "episodic" (eventos, decisões passadas)
  - content: o que deve ser lembrado
  - tags: lista de palavras-chave para facilitar a recuperação
- recall(query, limit): busca memórias relevantes para a query. Retorna as `limit` mais relevantes.

Instruções de comportamento:
1. No início de cada sessão, use recall() para verificar se há contexto relevante sobre o usuário.
2. Memorize preferências, decisões técnicas e contexto de projetos sempre que o usuário os mencionar.
3. Use as memórias para personalizar respostas — nunca trate o usuário como se fosse a primeira vez.
4. Se for memorizar algo, confirme brevemente ao usuário que guardou a informação.
5. Nunca invente memórias — só use o que foi retornado pelo recall().
```

---

## 🔄 Fluxo de Interação (passo a passo)

---

## SESSÃO 1 — Onboarding e Primeira Decisão Técnica

---

### Passo 1 — USUÁRIO: Apresentação e contexto do projeto

**Quem age:** Usuário
**O que acontece:** Na primeira sessão, o usuário se apresenta e pede ajuda para escolher uma biblioteca. Ele compartilha preferências e restrições sem perceber que está "ensinando" o agente.

```user
Oi! Vou usar você para me ajudar no dia a dia de desenvolvimento. Trabalho com Python,
prefiro soluções simples com pouca configuração, e odeio ORMs complexos. Estou começando
um novo microsserviço de API REST — qual framework você recomenda?
```

---

### Passo 2 — REASONING: Agente identifica o que deve memorizar

**Quem age:** Modelo (raciocínio interno)
**O que acontece:** Antes de responder, o agente identifica informações valiosas sobre o usuário que devem ser persistidas para sessões futuras.

```thinking
O usuário acabou de me dar várias informações valiosas sobre ele:
- Linguagem preferida: Python
- Valores: simplicidade, pouca configuração
- Aversão: ORMs complexos

Preciso guardar isso agora — em sessões futuras não terei esse contexto.
Vou usar remember() com type "semantic" para preferências gerais.

Depois de memorizar, posso responder com a recomendação.
Para um microsserviço simples em Python sem ORM complexo, FastAPI é a escolha natural:
minimalista, tipado, geração automática de docs.
```

---

### Passo 3 — TOOL CALL: Memorizar preferências do usuário (memória semântica)

**Quem age:** Modelo → Tool `remember`
**O que acontece:** O agente persiste as preferências do usuário na memória de longo prazo antes de responder à pergunta.

```tool_call
tool: remember
input: {
  "type": "semantic",
  "content": "Usuário trabalha com Python. Prefere soluções simples com pouca configuração. Tem aversão a ORMs complexos. Foco em microsserviços e APIs REST.",
  "tags": ["python", "preferências", "stack", "microsserviços"]
}
```

```tool_result
{
  "status": "stored",
  "memory_id": "mem_001",
  "type": "semantic",
  "content": "Usuário trabalha com Python. Prefere soluções simples com pouca configuração. Tem aversão a ORMs complexos. Foco em microsserviços e APIs REST."
}
```

---

### Passo 4 — MODELO: Resposta com recomendação técnica

**Quem age:** Modelo
**O que acontece:** Com as preferências salvas, o agente responde com uma recomendação personalizada.

```assistant
Dado o que você me contou — Python, simplicidade, sem ORM pesado — minha recomendação é
**FastAPI**.

Por quê faz sentido para você especificamente:
- Zero configuração para começar, estrutura minimalista
- Sem ORM embutido — você usa SQLite direto, psycopg2, ou qualquer coisa simples que preferir
- Validação automática com Pydantic (tipagem Python, sem magia)
- Docs geradas automaticamente (Swagger/ReDoc)

Para persistência leve, combina bem com **SQLModel** (do mesmo autor) ou simplesmente
queries SQL diretas com **asyncpg** se quiser async.

Quer que eu monte um esqueleto do projeto?

_Guardei suas preferências de stack para não precisar repetir isso nas próximas sessões. 🧠_
```

---

### Passo 5 — USUÁRIO: Confirmação da decisão técnica

**Quem age:** Usuário
**O que acontece:** O usuário confirma a escolha e adiciona detalhes do projeto. O agente deve memorizar essa decisão episódica.

```user
Perfeito, vou com FastAPI mesmo. O projeto se chama "freight-api" — é um serviço de
cotação de frete para e-commerce. Vou usar PostgreSQL com queries diretas, sem ORM.
```

---

### Passo 6 — TOOL CALL: Memorizar decisão do projeto (memória episódica)

**Quem age:** Modelo → Tool `remember`
**O que acontece:** O agente registra a decisão técnica como memória episódica — um evento concreto com contexto de projeto.

```tool_call
tool: remember
input: {
  "type": "episodic",
  "content": "Usuário iniciou projeto 'freight-api': serviço de cotação de frete para e-commerce. Stack escolhida: FastAPI + PostgreSQL com queries diretas (sem ORM). Decisão tomada na sessão inicial.",
  "tags": ["freight-api", "fastapi", "postgresql", "e-commerce", "frete"]
}
```

```tool_result
{
  "status": "stored",
  "memory_id": "mem_002",
  "type": "episodic",
  "content": "Usuário iniciou projeto 'freight-api': serviço de cotação de frete para e-commerce. Stack escolhida: FastAPI + PostgreSQL com queries diretas (sem ORM). Decisão tomada na sessão inicial."
}
```

---

### Passo 7 — MODELO: Confirmação e encerramento da Sessão 1

**Quem age:** Modelo
**O que acontece:** O agente confirma o que foi memorizado e a sessão termina. A janela de contexto será zerada na próxima vez.

```assistant
Ótimo! Registrado:

- **Projeto:** freight-api (cotação de frete para e-commerce)
- **Stack:** FastAPI + PostgreSQL com queries diretas

Da próxima vez que você abrir uma sessão, já vou saber o contexto sem precisar
perguntar de novo. Pode começar!
```

---
---

## SESSÃO 2 — Nova Sessão, Contexto Zerado

*(A janela de contexto foi reiniciada. O modelo não tem nenhuma mensagem anterior.
Sem memória de longo prazo, seria como se o usuário fosse desconhecido.)*

---

### Passo 8 — USUÁRIO: Pergunta direta sem repetir contexto

**Quem age:** Usuário
**O que acontece:** O usuário retorna dias depois e faz uma pergunta assumindo que o agente se lembra de tudo — como faria com um colega de trabalho. Não repete stack, projeto, nem preferências.

```user
Oi! Preciso adicionar autenticação JWT no projeto. Qual lib você recomenda?
```

---

### Passo 9 — REASONING: Agente percebe que precisa recuperar memórias

**Quem age:** Modelo (raciocínio interno)
**O que acontece:** O agente não tem contexto da sessão anterior. Antes de responder com uma sugestão genérica, ele usa `recall()` para verificar se há histórico relevante sobre este usuário.

```thinking
O usuário perguntou sobre JWT sem dar contexto de linguagem, framework, ou projeto.
Posso dar uma resposta genérica — mas isso seria tratar ele como um desconhecido.

Vou usar recall() primeiro para verificar se existe histórico sobre ele.
Query relevante: preferências de stack, projetos ativos.
```

---

### Passo 10 — TOOL CALL: Recuperar memórias relevantes

**Quem age:** Modelo → Tool `recall`
**O que acontece:** O agente busca na memória de longo prazo informações relevantes para personalizar a resposta sobre autenticação JWT.

```tool_call
tool: recall
input: {
  "query": "preferências de stack, linguagem, frameworks, projetos ativos",
  "limit": 3
}
```

```tool_result
{
  "memories": [
    {
      "memory_id": "mem_001",
      "type": "semantic",
      "relevance_score": 0.94,
      "content": "Usuário trabalha com Python. Prefere soluções simples com pouca configuração. Tem aversão a ORMs complexos. Foco em microsserviços e APIs REST."
    },
    {
      "memory_id": "mem_002",
      "type": "episodic",
      "relevance_score": 0.88,
      "content": "Usuário iniciou projeto 'freight-api': serviço de cotação de frete para e-commerce. Stack escolhida: FastAPI + PostgreSQL com queries diretas (sem ORM). Decisão tomada na sessão inicial."
    }
  ]
}
```

---

### Passo 11 — REASONING: Usando as memórias para personalizar a resposta

**Quem age:** Modelo (raciocínio interno)
**O que acontece:** Com o contexto recuperado, o agente agora sabe exatamente para qual cenário recomendar — FastAPI + Python, projeto freight-api, filosofia de simplicidade.

```thinking
Perfeito. Agora tenho o contexto completo:
- Linguagem: Python
- Framework: FastAPI (projeto freight-api)
- Filosofia: simplicidade, sem dependências pesadas

Para JWT com FastAPI em Python, a recomendação clara é `python-jose` (ou `PyJWT` se quiser
ainda mais minimalista) combinado com `passlib` para hashing de senha.

Vou mencionar o projeto pelo nome e contextualizar a sugestão para FastAPI — ele vai
perceber que me lembro de onde paramos.
```

---

### Passo 12 — MODELO: Resposta personalizada com contexto recuperado

**Quem age:** Modelo
**O que acontece:** O agente responde com uma recomendação específica para o contexto dele — FastAPI, Python, freight-api — como se a conversa nunca tivesse sido interrompida.

```assistant
Para o **freight-api** com FastAPI, recomendo essa combinação:

**`python-jose`** + **`passlib`**

```python
# requirements
python-jose[cryptography]
passlib[bcrypt]
```

Por que essa stack faz sentido para você:
- Zero configuração além de uma `SECRET_KEY` — sem banco extra, sem serviço externo
- `python-jose` é o padrão de fato no ecossistema FastAPI
- `passlib` para bcrypt no hash de senha — simples, seguro, sem ORM

Estrutura mínima:

```python
from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])

def create_token(user_id: str, secret: str) -> str:
    return jwt.encode({"sub": user_id}, secret, algorithm="HS256")
```

Quer que eu monte o endpoint de `/login` e o middleware de autenticação completo
para o freight-api?
```

---

## 📊 Resumo do Fluxo

| Passo | Sessão | Tipo | Agente | Descrição resumida |
|-------|--------|------|--------|--------------------|
| 1 | 1 | USUÁRIO | Usuário | Se apresenta, informa preferências e pede recomendação de framework |
| 2 | 1 | REASONING | Modelo | Identifica informações para memorizar antes de responder |
| 3 | 1 | TOOL CALL | Modelo → `remember` | Persiste preferências de stack (memória semântica) |
| 4 | 1 | MODELO | Modelo | Recomenda FastAPI baseado nas preferências; confirma que memorizou |
| 5 | 1 | USUÁRIO | Usuário | Confirma FastAPI, nomeia projeto "freight-api" e stack de banco |
| 6 | 1 | TOOL CALL | Modelo → `remember` | Persiste decisão do projeto (memória episódica) |
| 7 | 1 | MODELO | Modelo | Confirma o que foi memorizado e encerra a sessão |
| 8 | 2 | USUÁRIO | Usuário | Nova sessão; pergunta sobre JWT sem repetir contexto |
| 9 | 2 | REASONING | Modelo | Percebe ausência de contexto; decide usar recall() antes de responder |
| 10 | 2 | TOOL CALL | Modelo → `recall` | Recupera memórias semântica e episódica com relevância alta |
| 11 | 2 | REASONING | Modelo | Usa memórias para contextualizar a resposta para FastAPI/freight-api |
| 12 | 2 | MODELO | Modelo | Resposta personalizada que referencia o projeto pelo nome |

---

## ❌ Modo Falha — Sem Memória de Longo Prazo

Para contraste didático: o que aconteceria no Passo 8 se o agente **não tivesse** ferramentas de memória?

```user
Oi! Preciso adicionar autenticação JWT no projeto. Qual lib você recomenda?
```

```assistant
[SEM MEMÓRIA]

Para autenticação JWT, existem boas opções dependendo da sua linguagem e framework:

- **Python:** python-jose ou PyJWT
- **Node.js:** jsonwebtoken
- **Go:** golang-jwt

Qual linguagem você está usando?
```

**Problemas evidentes:**
- Trata o usuário como desconhecido em cada sessão
- Perde o contexto do projeto (freight-api, FastAPI, PostgreSQL)
- Gera fricção desnecessária: o usuário precisa repetir contexto sempre
- Não aprende preferências ao longo do tempo
- Respostas genéricas onde poderiam ser altamente personalizadas

---

## 💡 Conceitos Ilustrados

- **Memória de curto prazo (janela de contexto):** as mensagens da sessão atual — efêmera, zerada ao fechar a sessão; é a única memória que modelos têm por padrão
- **Memória de longo prazo:** armazenamento externo acessado via ferramentas — persiste entre sessões e dá ao agente continuidade real
- **Memória semântica:** conhecimento geral sobre o usuário — preferências, valores, estilo de trabalho; não depende de um evento específico
- **Memória episódica:** registro de eventos e decisões — "o que aconteceu", "o que foi decidido"; tem data, contexto e causa
- **`remember()` como escrita ativa:** o agente decide proativamente o que vale guardar — não memoriza tudo, só o relevante; seletividade é uma capacidade do modelo
- **`recall()` como recuperação semântica:** a busca é por similaridade de conteúdo, não por chave exata — o agente não sabe de antemão quais memórias existem
- **Grounding em memória:** o agente só usa o que `recall()` retorna — nunca inventa histórico; mesma filosofia do grounding em RAG
- **Personalização vs. privacidade:** este fluxo naturalmente levanta a questão de controle do usuário sobre suas memórias — dado importante para discutir em aula
