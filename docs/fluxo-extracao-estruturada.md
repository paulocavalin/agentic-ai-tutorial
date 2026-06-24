# Fluxo: Extração de Dados Estruturados com Agente

## Visão Geral

Este fluxo demonstra um **Agente de Processamento de Documentos** que recebe texto não estruturado (nota fiscal, contrato, e-mail) e extrai campos em formato JSON validado.

O mecanismo-chave: o agente usa **tool calling como mecanismo de saída estruturada** — a LLM é forçada a preencher um schema predefinido ao invés de gerar texto livre.

```
Texto não estruturado                 Agente                    Output JSON
        │                               │                            │
        │  "Nota Fiscal ACME Corp,      │                            │
        │   R$ 4.800,00, 4 itens..."    │                            │
        │──────────────────────────────►│                            │
        │                               │ [analisa texto]            │
        │                               │ [chama extract_invoice()]  │
        │                               │────────────────────────────►
        │                               │                            │
        │                               │ {"vendor": "ACME Corp",    │
        │                               │  "total": 4800.00,         │
        │                               │  "items": [...]}           │
        │◄──────────────────────────────│◄───────────────────────────│
        │  JSON validado                │                            │
```

**Padrão:** Tool Calling como Structured Output — a ferramenta define o schema; a LLM preenche.

---

## Por que usar Tool Calling para extração?

| Abordagem | Problema |
|-----------|---------|
| Pedir JSON em linguagem natural | LLM pode adicionar texto antes/depois, quebrar o JSON, inventar campos |
| `response_format: json_object` | Garante JSON válido, mas não valida o schema |
| **Tool Calling** | LLM preenche os parâmetros definidos no schema → saída tipada, validada, previsível |

```
# Sem tool calling: LLM pode gerar:
"Aqui está o JSON extraído: ```json\n{\"vendor\": \"ACME\"...```\n\nObs: o campo 'due_date' não estava no texto."

# Com tool calling: LLM produz chamada de ferramenta com parâmetros estruturados:
{
  "tool": "extract_invoice",
  "arguments": {
    "vendor": "ACME Corp",
    "total": 4800.00,
    "due_date": null,  ← null explícito, não alucinado
    "items": [...]
  }
}
```

---

## Schema de Extração (Nota Fiscal)

```json
{
  "vendor": "string | null",
  "invoice_number": "string | null",
  "issue_date": "YYYY-MM-DD | null",
  "due_date": "YYYY-MM-DD | null",
  "currency": "BRL | USD | EUR",
  "subtotal": "number | null",
  "tax_amount": "number | null",
  "total": "number",
  "items": [
    {
      "description": "string",
      "quantity": "number",
      "unit_price": "number",
      "line_total": "number"
    }
  ],
  "notes": "string | null",
  "confidence": "high | medium | low"
}
```

> O campo `confidence` é preenchido pela própria LLM, indicando sua certeza sobre a extração. Útil para triagem de revisão humana.

---

## System Prompt do Agente

```
Você é um agente especialista em processamento de documentos financeiros.

Sua única função é extrair campos estruturados de textos de documentos.

REGRAS:
1. Use SEMPRE a ferramenta de extração fornecida. Nunca responda em texto livre.
2. Para campos não encontrados no texto, use null. NUNCA invente valores.
3. Normalize datas para YYYY-MM-DD.
4. Normalize valores monetários para números (remova R$, vírgulas como separadores de milhar).
5. Se o texto for ambíguo, escolha o valor mais plausível e defina confidence como "low".
6. Se o texto claramente não é uma nota fiscal, retorne um objeto vazio com confidence "low".
```

---

## Cenário A: Extração bem-sucedida

**Texto de entrada:**

```
NOTA FISCAL ELETRÔNICA
Emitente: ACME Tecnologia Ltda | CNPJ: 12.345.678/0001-99
Data de emissão: 15/01/2025 | Vencimento: 30/01/2025
NF-e nº 004521

Itens:
- Licença Software Pro (12 meses) | Qtd: 2 | R$ 1.200,00 | Subtotal: R$ 2.400,00
- Suporte Técnico Premium (anual)  | Qtd: 1 | R$ 1.800,00 | Subtotal: R$ 1.800,00
- Treinamento EAD (turma)          | Qtd: 3 | R$ 200,00   | Subtotal: R$ 600,00

Subtotal: R$ 4.800,00
ISS (5%): R$ 240,00
TOTAL: R$ 5.040,00

Observações: Pagamento via PIX ou boleto. Dados bancários no portal.
```

### Passo 1 — LLM analisa e chama a ferramenta

**Quem age:** Agente (raciocínio interno + chamada de ferramenta)

```
Agente → Sistema
role: "assistant"
<thinking>
Documento de nota fiscal. Identifico:
- Emitente: ACME Tecnologia Ltda
- Data de emissão: 15/01/2025 → 2025-01-15
- Vencimento: 30/01/2025 → 2025-01-30
- 3 itens com quantidades e preços
- Subtotal: 4800.00
- ISS: 240.00
- Total: 5040.00
Todos os campos principais presentes → confidence: "high"
</thinking>

{
  "tool": "extract_invoice",
  "arguments": {
    "vendor": "ACME Tecnologia Ltda",
    "invoice_number": "004521",
    "issue_date": "2025-01-15",
    "due_date": "2025-01-30",
    "currency": "BRL",
    "subtotal": 4800.00,
    "tax_amount": 240.00,
    "total": 5040.00,
    "items": [
      {
        "description": "Licença Software Pro (12 meses)",
        "quantity": 2,
        "unit_price": 1200.00,
        "line_total": 2400.00
      },
      {
        "description": "Suporte Técnico Premium (anual)",
        "quantity": 1,
        "unit_price": 1800.00,
        "line_total": 1800.00
      },
      {
        "description": "Treinamento EAD (turma)",
        "quantity": 3,
        "unit_price": 200.00,
        "line_total": 600.00
      }
    ],
    "notes": "Pagamento via PIX ou boleto.",
    "confidence": "high"
  }
}
```

### Passo 2 — Validação automática

**Quem age:** Sistema (validação de schema + regras de negócio)

```
Sistema → Agente
role: "tool"

{
  "status": "valid",
  "checks": {
    "schema": "passed",
    "line_items_sum": "passed (4800.00 == 2400 + 1800 + 600)",
    "total_calculation": "passed (5040.00 == 4800 + 240)",
    "date_logic": "passed (issue_date < due_date)"
  }
}
```

### Passo 3 — Resposta final

**Quem age:** Agente

```
Agente → Usuário
role: "assistant"

Extração concluída com confiança alta.

{
  "vendor": "ACME Tecnologia Ltda",
  "invoice_number": "004521",
  "issue_date": "2025-01-15",
  "due_date": "2025-01-30",
  "currency": "BRL",
  "subtotal": 4800.00,
  "tax_amount": 240.00,
  "total": 5040.00,
  "items": [
    {"description": "Licença Software Pro (12 meses)", "quantity": 2, "unit_price": 1200.00, "line_total": 2400.00},
    {"description": "Suporte Técnico Premium (anual)",  "quantity": 1, "unit_price": 1800.00, "line_total": 1800.00},
    {"description": "Treinamento EAD (turma)",          "quantity": 3, "unit_price": 200.00,  "line_total": 600.00}
  ],
  "notes": "Pagamento via PIX ou boleto.",
  "confidence": "high"
}
```

---

## Cenário B: Campos ausentes → null explícito (sem alucinação)

**Texto de entrada (incompleto):**

```
Recibo de pagamento
Fornecedor: João Silva ME
Valor recebido: R$ 350,00
Ref: Consultoria março/2025
```

**Extração do agente:**

```json
{
  "vendor": "João Silva ME",
  "invoice_number": null,
  "issue_date": null,
  "due_date": null,
  "currency": "BRL",
  "subtotal": null,
  "tax_amount": null,
  "total": 350.00,
  "items": [
    {
      "description": "Consultoria março/2025",
      "quantity": 1,
      "unit_price": 350.00,
      "line_total": 350.00
    }
  ],
  "notes": null,
  "confidence": "medium"
}
```

> 💡 **Conceito-chave:** A LLM usa `null` explicitamente para campos ausentes.  
> Sem a disciplina do schema, ela poderia **alucinar** `"invoice_number": "001"` ou `"issue_date": "2025-03-01"`.

---

## Cenário C: Conflito de dados → confidence "low" + flag

**Texto de entrada (inconsistente):**

```
Nota Fiscal 
Total dos itens: R$ 1.000,00
Desconto aplicado: R$ 200,00
TOTAL A PAGAR: R$ 950,00   ← inconsistente (deveria ser 800,00)
```

**Extração do agente:**

```json
{
  "vendor": null,
  "invoice_number": null,
  "issue_date": null,
  "due_date": null,
  "currency": "BRL",
  "subtotal": 1000.00,
  "tax_amount": -200.00,
  "total": 950.00,
  "items": [],
  "notes": "ATENÇÃO: inconsistência detectada. Subtotal (1000) - Desconto (200) = 800, mas total informado é 950.",
  "confidence": "low"
}
```

> 💡 **Conceito-chave:** O agente detecta a inconsistência, preserva os valores do documento sem corrigi-los, e **sinaliza para revisão humana** via `confidence: "low"` e nota explicativa.

---

## Resumo do Fluxo

| Passo | Agente age | Ferramenta | Output |
|-------|-----------|-----------|--------|
| 1 | Analisa texto, identifica tipo de documento | — | Plano interno |
| 2 | Chama ferramenta de extração com campos preenchidos | `extract_invoice` | JSON estruturado |
| 3 | Validação de schema e regras de negócio | `validate_extraction` | Relatório de checks |
| 4 | Resposta final ao usuário | — | JSON + status |

---

## Conceitos Ilustrados

| Conceito | Onde aparece |
|----------|-------------|
| **Tool calling como structured output** | Schema da ferramenta força a LLM a preencher campos tipados |
| **null explícito vs. alucinação** | Cenário B: campos ausentes recebem null, não valores inventados |
| **Confidence scoring** | Campo `confidence` preenchido pela LLM, permite triagem automática |
| **Validação downstream** | Tool `validate_extraction` checa consistência matemática dos dados |
| **Detecção de conflito** | Cenário C: agente sinaliza inconsistência sem "corrigir" os dados |
| **Normalização** | Datas → ISO 8601; valores → float sem símbolos de moeda |
| **Documento não reconhecido** | Se não é nota fiscal, retorna objeto vazio com `confidence: "low"` |
