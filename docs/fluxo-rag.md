# 📚 Simulação de Fluxo Agêntico — RAG (Retrieval-Augmented Generation)

---

## 🗺️ Visão Geral do Sistema

**Cenário:** Um assistente interno de RH que responde perguntas sobre políticas da empresa. Sem RAG, o modelo responderia com informações genéricas ou inventadas. Com RAG, ele consulta uma base de conhecimento interna antes de responder — e só afirma o que encontrou nos documentos.

O fluxo contrasta dois caminhos lado a lado: **com RAG** e **sem RAG**.

```
Usuário
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│                    PIPELINE RAG                                  │
│                                                                  │
│  1. INDEXAÇÃO (offline, feita antes das perguntas)              │
│     Documentos → Chunks → Embeddings → Armazenados no vetor DB  │
│                                                                  │
│  2. CONSULTA (online, a cada pergunta)                           │
│     Pergunta → Embedding → Busca por similaridade → Top-K chunks │
│                                │                                 │
│                                ▼                                 │
│     Chunks relevantes + Pergunta → Prompt enriquecido → LLM     │
│                                                                  │
│     LLM → Resposta fundamentada nos documentos                  │
└──────────────────────────────────────────────────────────────────┘
```

**Comparação: com e sem RAG**

```
SEM RAG                         COM RAG
───────────────────             ────────────────────────────────
Usuário → LLM                   Usuário → Retriever → LLM
                                              │
                                         Vetor DB
                                         (documentos indexados)

Resultado: resposta genérica    Resultado: resposta fundamentada
ou alucinação                   com trechos do documento
```

**Componentes envolvidos:**
- **Embedding Model:** transforma texto em vetores (ex: `text-embedding-3-small`, `nomic-embed-text`)
- **Vector Store:** banco que armazena e busca vetores por similaridade (ex: FAISS, Chroma, pgvector)
- **Retriever:** busca os K chunks mais similares à pergunta do usuário
- **LLM:** gera a resposta final usando os chunks como contexto
- **Documentos de origem:** PDFs, páginas internas, manuais — a base de conhecimento real

---

## 📐 Etapas do RAG

| Etapa | Quando ocorre | O que acontece |
|-------|--------------|----------------|
| **Chunking** | Offline (ingestão) | Documento é dividido em trechos de ~500 tokens com sobreposição |
| **Embedding** | Offline (ingestão) | Cada chunk é convertido em um vetor de alta dimensão |
| **Indexação** | Offline (ingestão) | Vetores são armazenados no vector store com metadados |
| **Query embedding** | Online (por pergunta) | A pergunta do usuário também é convertida em vetor |
| **Similarity search** | Online (por pergunta) | Vetores mais próximos da query são recuperados (cosine/dot product) |
| **Context injection** | Online (por pergunta) | Chunks recuperados são inseridos no prompt do LLM |
| **Generation** | Online (por pergunta) | LLM gera resposta fundamentada nos chunks |

---

## ⚙️ System Prompt

```system
Você é um assistente interno de RH da empresa. Responda perguntas dos colaboradores
sobre políticas, benefícios e procedimentos da empresa.

REGRA FUNDAMENTAL: Responda SOMENTE com base nos documentos fornecidos no contexto.
- Se a informação estiver no contexto: responda de forma clara e cite o documento de origem.
- Se a informação NÃO estiver no contexto: diga explicitamente "Essa informação não está
  disponível na base de conhecimento atual. Consulte o RH diretamente."
- NUNCA invente políticas, valores, prazos ou benefícios que não estejam nos documentos.
- Se o contexto for parcial, responda com o que está disponível e sinalize o que ficou pendente.

Formato de citação: "Conforme [nome do documento], seção [X]: ..."
```

---

## 🔄 Fluxo de Interação (passo a passo)

---

## FASE 1 — Indexação (Offline)

*Esta fase acontece uma vez, antes das perguntas dos usuários. É a "preparação" da base de conhecimento.*

---

### Passo 1 — SISTEMA: Carregamento e divisão dos documentos (Chunking)

**Quem age:** Pipeline de ingestão (sistema)
**O que acontece:** Os documentos da empresa são carregados e divididos em chunks menores, com sobreposição para não perder contexto entre trechos.

```system
[Ingestão — Documentos carregados]
- manual_beneficios_2025.pdf       → 48 páginas
- politica_ferias_licencas.pdf     → 12 páginas
- codigo_conduta_etica.pdf         → 22 páginas
- guia_onboarding.pdf              → 15 páginas

[Chunking]
Estratégia: tamanho = 512 tokens | sobreposição = 64 tokens
manual_beneficios_2025.pdf → 94 chunks
politica_ferias_licencas.pdf → 21 chunks
codigo_conduta_etica.pdf → 38 chunks
guia_onboarding.pdf → 28 chunks

Total: 181 chunks gerados
```

---

### Passo 2 — SISTEMA: Geração de embeddings e indexação no vector store

**Quem age:** Pipeline de ingestão (sistema)
**O que acontece:** Cada chunk é transformado em um vetor de alta dimensão pelo modelo de embedding. Os vetores são armazenados no vector store junto com os metadados do chunk original.

```system
[Embedding]
Modelo: nomic-embed-text (768 dimensões)
Processando 181 chunks...

Exemplo — chunk #47 (manual_beneficios_2025.pdf, p.18):
  Texto: "O plano de saúde corporativo cobre o colaborador e até 3 dependentes..."
  Vetor: [0.023, -0.411, 0.887, 0.102, ..., -0.234]  (768 dimensões)

[Indexação no Vector Store]
Vector Store: FAISS (in-memory)
181 vetores armazenados com metadados:
  {chunk_id, source_file, page, chunk_index, text}

Status: Base de conhecimento pronta ✓
```

---

## FASE 2 — Consulta (Online, por pergunta)

---

### Passo 3 — USUÁRIO: Pergunta sobre benefícios

**Quem age:** Usuário (colaborador)
**O que acontece:** Um novo funcionário faz uma pergunta sobre o plano de saúde. A pergunta entra no pipeline RAG.

```user
Quantos dependentes posso incluir no plano de saúde da empresa?
Minha esposa e dois filhos se qualificam?
```

---

### Passo 4 — SISTEMA: Embedding da pergunta

**Quem age:** Pipeline RAG (retriever)
**O que acontece:** A pergunta do usuário é convertida pelo mesmo modelo de embedding usado na indexação. Isso coloca a pergunta no mesmo espaço vetorial dos chunks.

```system
[Query Embedding]
Input: "Quantos dependentes posso incluir no plano de saúde da empresa?
        Minha esposa e dois filhos se qualificam?"

Modelo: nomic-embed-text
Query vector: [0.031, -0.398, 0.901, 0.088, ..., -0.219]  (768 dimensões)
```

---

### Passo 5 — SISTEMA: Busca por similaridade no vector store

**Quem age:** Pipeline RAG (retriever)
**O que acontece:** O vetor da pergunta é comparado com os 181 vetores indexados usando similaridade de cosseno. Os K chunks mais próximos são recuperados.

```system
[Similarity Search]
Métrica: cosine similarity
Buscando os 3 chunks mais similares...

Resultado (Top-3):
┌─────┬──────────────────────────────────────────┬───────────┬────────────┐
│ Rank│ Fonte                                    │ Página    │ Similaridade│
├─────┼──────────────────────────────────────────┼───────────┼────────────┤
│  1  │ manual_beneficios_2025.pdf               │ p.18      │   0.94     │
│  2  │ manual_beneficios_2025.pdf               │ p.19      │   0.87     │
│  3  │ guia_onboarding.pdf                      │ p.6       │   0.71     │
└─────┴──────────────────────────────────────────┴───────────┴────────────┘

Chunks recuperados:

[Chunk 1 — manual_beneficios_2025.pdf, p.18, similaridade: 0.94]
"O plano de saúde corporativo (Bradesco Saúde — Plano Empresarial Gold) cobre
o colaborador titular e até 3 (três) dependentes diretos. Dependentes elegíveis:
cônjuge ou companheiro(a) com união estável comprovada, filhos biológicos ou
adotivos até 24 anos, e filhos com deficiência sem limite de idade. A inclusão
deve ser solicitada ao RH em até 30 dias após a contratação ou ocorrência do
evento (casamento, nascimento, adoção)."

[Chunk 2 — manual_beneficios_2025.pdf, p.19, similaridade: 0.87]
"Custo do plano: a empresa cobre 100% do plano do titular. Para cada dependente,
o colaborador contribui com 30% do valor da mensalidade, descontado em folha.
Reajuste anual em janeiro, conforme tabela ANS. Para inclusão de dependente após
o prazo de 30 dias, o colaborador aguarda o período de carência contratual."

[Chunk 3 — guia_onboarding.pdf, p.6, similaridade: 0.71]
"Benefícios ativos a partir do 1º dia de trabalho: vale-refeição, vale-transporte
e plano de saúde. Para ativar o plano de saúde e incluir dependentes, acesse o
portal RH (rh.empresa.com) e preencha o formulário de adesão em até 30 dias."
```

---

### Passo 6 — SISTEMA: Montagem do prompt enriquecido

**Quem age:** Pipeline RAG
**O que acontece:** Os 3 chunks recuperados são inseridos no prompt enviado ao LLM junto com a pergunta original. O LLM só "vê" esses trechos — não acessa os documentos completos diretamente.

```system
[Prompt enviado ao LLM]

SYSTEM:
Você é um assistente interno de RH da empresa. Responda SOMENTE com base nos
documentos fornecidos no contexto. Se a informação não estiver no contexto, diga
explicitamente que não está disponível na base de conhecimento.

CONTEXTO RECUPERADO:
---
[Fonte: manual_beneficios_2025.pdf, p.18]
O plano de saúde corporativo (Bradesco Saúde — Plano Empresarial Gold) cobre o colaborador
titular e até 3 (três) dependentes diretos. Dependentes elegíveis: cônjuge ou companheiro(a)
com união estável comprovada, filhos biológicos ou adotivos até 24 anos, e filhos com
deficiência sem limite de idade. A inclusão deve ser solicitada ao RH em até 30 dias após a
contratação ou ocorrência do evento (casamento, nascimento, adoção).

[Fonte: manual_beneficios_2025.pdf, p.19]
Custo do plano: a empresa cobre 100% do plano do titular. Para cada dependente, o colaborador
contribui com 30% do valor da mensalidade, descontado em folha. Reajuste anual em janeiro,
conforme tabela ANS. Para inclusão de dependente após o prazo de 30 dias, o colaborador
aguarda o período de carência contratual.

[Fonte: guia_onboarding.pdf, p.6]
Benefícios ativos a partir do 1º dia de trabalho. Para ativar o plano de saúde e incluir
dependentes, acesse o portal RH (rh.empresa.com) e preencha o formulário de adesão em até
30 dias.
---

USER:
Quantos dependentes posso incluir no plano de saúde da empresa?
Minha esposa e dois filhos se qualificam?
```

---

### Passo 7 — MODELO: Resposta fundamentada (com RAG)

**Quem age:** LLM
**O que acontece:** O LLM gera uma resposta usando apenas as informações presentes nos chunks. Ele não inventa dados — só sintetiza o que encontrou nos documentos.

```assistant
[COM RAG] ✅

Sim, sua situação está dentro do previsto. Veja o que diz o manual:

**Cobertura para dependentes**
Conforme o *Manual de Benefícios 2025* (p.18), o plano de saúde cobre até **3 dependentes diretos**. Sua esposa e seus dois filhos se qualificam:
- **Esposa:** elegível como cônjuge (ou companheira com união estável comprovada)
- **Filhos:** elegíveis até 24 anos (biológicos ou adotivos); sem limite de idade em caso de deficiência

**Custo**
A empresa cobre 100% do plano do titular. Para cada dependente, você contribui com **30% da mensalidade**, descontado em folha (p.19).

**Como incluir**
Acesse o portal RH em **rh.empresa.com** e preencha o formulário de adesão. O prazo é de **30 dias** a partir da contratação ou do evento (casamento, nascimento). Após esse prazo, é necessário aguardar o período de carência contratual.

*Fonte: Manual de Benefícios 2025, p.18–19; Guia de Onboarding, p.6*
```

---

## ❌ Modo Falha — Sem RAG (Alucinação)

Para contraste didático: o que aconteceria com a **mesma pergunta** enviada diretamente ao LLM, sem recuperação de documentos?

```user
Quantos dependentes posso incluir no plano de saúde da empresa?
Minha esposa e dois filhos se qualificam?
```

```assistant
[SEM RAG] ⚠️ Alucinação

A maioria dos planos de saúde corporativos permite incluir entre 2 e 5 dependentes,
geralmente cônjuge e filhos menores de 18 ou 21 anos. Consulte o setor de RH ou o
portal de benefícios da empresa para verificar os critérios específicos do seu plano.
```

**Problemas evidentes:**
- Inventou "2 a 5 dependentes" — o número real é até 3
- Inventou "menores de 18 ou 21 anos" — o real é até 24 anos
- Não sabia o nome da operadora (Bradesco Saúde) nem o plano (Gold)
- Não mencionou o custo de 30% por dependente
- A resposta parece confiante, mas está incorreta em detalhes críticos

---

### Passo 8 — USUÁRIO: Segunda pergunta (informação ausente na base)

**Quem age:** Usuário
**O que acontece:** O usuário faz uma segunda pergunta sobre algo que não está nos documentos indexados. O sistema RAG deve reconhecer a lacuna e não inventar.

```user
Qual é o valor mensal do plano para cada dependente?
```

---

### Passo 9 — SISTEMA: Busca retorna resultado de baixa similaridade

**Quem age:** Pipeline RAG (retriever)
**O que acontece:** A busca retorna o chunk mais próximo, mas a similaridade é baixa — o valor em reais não está nos documentos indexados.

```system
[Similarity Search]
Top-1: manual_beneficios_2025.pdf, p.19 | similaridade: 0.52

[Chunk recuperado]
"Custo do plano: a empresa cobre 100% do plano do titular. Para cada dependente, o
colaborador contribui com 30% do valor da mensalidade, descontado em folha. Reajuste
anual em janeiro, conforme tabela ANS."

⚠️ Nota: similaridade abaixo do threshold (0.65) — conteúdo pode não responder a pergunta.
```

---

### Passo 10 — MODELO: Resposta honesta sobre lacuna (com RAG)

**Quem age:** LLM
**O que acontece:** O LLM identifica que os documentos mencionam o percentual (30%), mas não o valor absoluto em reais — e diz isso claramente ao invés de inventar.

```assistant
[COM RAG — lacuna identificada] ✅

Os documentos informam que cada dependente corresponde a **30% do valor da mensalidade do plano**,
descontado em folha. O reajuste ocorre anualmente em janeiro, conforme a tabela ANS.

Porém, **o valor absoluto em reais não está disponível na base de conhecimento atual** —
pode variar conforme a faixa etária do dependente e a data de reajuste vigente.

Para consultar o valor exato, acesse o portal RH em **rh.empresa.com** ou entre em contato
diretamente com o setor de benefícios.

*Fonte: Manual de Benefícios 2025, p.19*
```

---

## 📊 Resumo do Fluxo

### Fase 1 — Indexação (offline)

| Passo | Tipo | Quem age | Descrição resumida |
|-------|------|----------|--------------------|
| 1 | SISTEMA | Pipeline | Carrega documentos e divide em 181 chunks (512 tokens, overlap 64) |
| 2 | SISTEMA | Pipeline | Gera embeddings com nomic-embed-text (768d) e indexa no FAISS |

### Fase 2 — Consulta (online)

| Passo | Tipo | Quem age | Descrição resumida |
|-------|------|----------|--------------------|
| 3 | USUÁRIO | Usuário | Pergunta sobre dependentes no plano de saúde |
| 4 | SISTEMA | Retriever | Converte pergunta em vetor com o mesmo modelo de embedding |
| 5 | SISTEMA | Retriever | Busca por similaridade coseno → recupera Top-3 chunks |
| 6 | SISTEMA | Pipeline | Monta prompt enriquecido: chunks + pergunta original |
| 7 | MODELO | LLM | Gera resposta fundamentada nos documentos com citação de fonte |
| 8 | USUÁRIO | Usuário | Segunda pergunta sobre valor em reais |
| 9 | SISTEMA | Retriever | Busca retorna chunk com baixa similaridade (0.52 < threshold) |
| 10 | MODELO | LLM | Responde com o que há nos docs e sinaliza lacuna explicitamente |

---

## 💡 Conceitos Ilustrados

- **Chunking:** por que documentos inteiros não cabem no contexto do LLM — e como a divisão em trechos menores viabiliza a busca
- **Embedding:** a transformação de texto em vetor é o que permite comparar semântica, não palavras exatas — "cônjuge" e "esposa" ficam próximos no espaço vetorial
- **Similarity search:** o retriever não faz busca por palavra-chave; compara geometria vetorial — chunks semanticamente relevantes são recuperados mesmo sem match exato
- **Context injection:** o LLM só vê os chunks recuperados, não os documentos completos — o retriever faz a pré-seleção
- **Grounding vs. alucinação:** RAG fundamenta a resposta em fontes verificáveis; sem RAG o modelo responde com confiança incorreta (Passo 7 vs. modo falha)
- **Lacuna honesta (Passos 9–10):** RAG bem implementado reconhece o que não está na base — tão importante quanto responder corretamente o que está
- **Threshold de similaridade:** scores abaixo de um limiar indicam que os chunks recuperados podem não ser relevantes — o sistema deve sinalizar isso ao LLM
- **Separação offline/online:** indexação é cara (feita uma vez); consulta é barata (feita a cada pergunta) — essa assimetria é central para escalar RAG em produção
