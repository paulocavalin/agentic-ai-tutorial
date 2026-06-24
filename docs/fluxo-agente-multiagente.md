# 🤖 Simulação de Fluxo Agêntico — Sistema Multi-Agente (Orquestrador + Sub-agentes)

---

## 🗺️ Visão Geral do Sistema

**Cenário:** Um sistema de análise de incidentes de segurança em produção. Um agente orquestrador recebe o alerta, identifica que precisa de expertise especializada, e delega para dois sub-agentes: um para análise técnica dos logs e outro para redigir o relatório de incidente. Ilustra como sistemas multi-agente distribuem responsabilidades.

```
Usuário (engenheiro de plantão)
  │
  ▼
🟦 AGENTE ORQUESTRADOR
  │
  ├─► [REASONING] Avalia incidente e decide delegar
  │
  ├─► tool: delegate_to_agent("log-analyzer", contexto)
  │       │
  │       ▼
  │   🟨 SUB-AGENTE: Log Analyzer
  │       ├─► tool: fetch_logs(service, time_range)
  │       ├─► tool: run_query(log_data, pattern)
  │       └─► retorna: análise estruturada
  │
  ├─► [REASONING] Recebe análise, decide próximo sub-agente
  │
  ├─► tool: delegate_to_agent("report-writer", análise)
  │       │
  │       ▼
  │   🟩 SUB-AGENTE: Report Writer
  │       ├─► MCP: confluence__create_page(título, conteúdo)
  │       └─► retorna: URL da página criada
  │
  └─► Resposta consolidada ao usuário
```

**Componentes envolvidos:**
- **Agente Orquestrador:** coordena o fluxo, decide o que delegar e a quem
- **Sub-agente Log Analyzer:** especializado em análise de logs e detecção de padrões
- **Sub-agente Report Writer:** especializado em documentação técnica via Confluence (MCP)
- **Tool:** `delegate_to_agent` — mecanismo que o orquestrador usa para chamar sub-agentes
- **MCP Server:** Confluence — criação de páginas de documentação

---

## ⚙️ System Prompt

### Orquestrador

```system
Você é um orquestrador de resposta a incidentes de produção.

Seu papel é coordenar a investigação e resolução de incidentes, delegando tarefas para
sub-agentes especializados conforme necessário.

Sub-agentes disponíveis (via delegate_to_agent):
- "log-analyzer": especializado em buscar e analisar logs de sistemas. Recebe: {service, time_range, hypothesis}
- "report-writer": especializado em documentar incidentes. Recebe: {incident_summary, analysis, recommendations}

Ferramenta disponível:
- delegate_to_agent(agent_name, task_context): delega uma tarefa a um sub-agente e aguarda o resultado.

Instruções:
1. Avalie o incidente e decida quais sub-agentes são necessários e em que ordem.
2. Passe contexto suficiente para cada sub-agente — eles não têm acesso ao histórico desta conversa.
3. Sintetize os resultados dos sub-agentes antes de responder ao usuário.
4. Nunca execute ações técnicas diretas — delegue sempre para o sub-agente correto.
```

### Sub-agente: Log Analyzer

```system
Você é um especialista em análise de logs de sistemas distribuídos.
Você tem acesso às ferramentas: fetch_logs(service, time_range) e run_query(log_data, pattern).
Retorne sempre uma análise estruturada com: root_cause_hypothesis, affected_components, timeline, severity.
```

### Sub-agente: Report Writer

```system
Você é um especialista em documentação técnica de incidentes.
Você tem acesso ao servidor MCP do Confluence para criar páginas de documentação.
Use o template padrão de Post-Mortem: Summary, Timeline, Root Cause, Impact, Action Items.
```

---

## 🔄 Fluxo de Interação (passo a passo)

---

### Passo 1 — USUÁRIO: Alerta de incidente

**Quem age:** Usuário
**O que acontece:** O engenheiro de plantão recebe um alerta de monitoramento e aciona o agente orquestrador com o contexto básico do incidente.

```user
Temos um incidente em produção. O serviço de pagamentos (payment-service) está com taxa
de erro acima de 40% desde as 14h15. Já fizemos rollback mas os erros continuaram por
mais 20 minutos. Preciso entender a causa raiz e gerar o post-mortem.
```

---

### Passo 2 — REASONING: Orquestrador avalia e planeja delegação

**Quem age:** Agente Orquestrador (raciocínio interno)
**O que acontece:** O orquestrador interpreta o incidente e decide o plano de delegação: primeiro o log-analyzer para entender a causa raiz, depois o report-writer para documentar.

```thinking
Incidente no payment-service, 40% error rate, período: ~14h15 até ~14h35 (rollback + 20min).
O rollback não resolveu imediatamente — isso sugere que a causa pode ser externa ao serviço
(banco de dados, dependência downstream, dados corrompidos).

Meu plano de delegação:
1. log-analyzer: buscar logs do payment-service no período 14h00–15h00, hipótese inicial: dependência externa
2. report-writer: com base na análise, criar o post-mortem no Confluence

Vou passar contexto completo para o log-analyzer — ele não sabe nada desta conversa.
```

---

### Passo 3 — TOOL CALL (local): Delegação para sub-agente de logs

**Quem age:** Orquestrador → Tool `delegate_to_agent`
**O que acontece:** O orquestrador delega a investigação dos logs ao sub-agente especializado, passando todo o contexto necessário para que ele opere de forma autônoma.

```tool_call
tool: delegate_to_agent
input: {
  "agent_name": "log-analyzer",
  "task_context": {
    "service": "payment-service",
    "time_range": "2025-03-19T14:00:00-03:00 / 2025-03-19T15:00:00-03:00",
    "hypothesis": "Causa pode ser dependência externa — rollback não resolveu imediatamente",
    "task": "Analise os logs do payment-service nesse período e identifique a causa raiz dos erros. Retorne análise estruturada com root_cause_hypothesis, affected_components, timeline e severity."
  }
}
```

---

### Passo 4 — SUB-AGENTE (Log Analyzer): Execução interna

**Quem age:** Sub-agente Log Analyzer (execução interna)
**O que acontece:** O sub-agente executa de forma autônoma, buscando logs e rodando queries de análise. O orquestrador aguarda o resultado — ele não interfere nesse processo.

```thinking
[INTERNO — Sub-agente Log Analyzer]
Recebi o contexto do orquestrador. Vou buscar os logs do payment-service no período indicado
e rodar queries para encontrar padrões de erro.
```

```tool_call
tool: fetch_logs
input: {
  "service": "payment-service",
  "time_range": "14:00-15:00",
  "level": "ERROR"
}
```

```tool_result
[14:12] WARN  payment-service: db-connection-pool utilization at 89%
[14:15] ERROR payment-service: timeout connecting to fraud-check-api (attempt 1/3)
[14:15] ERROR payment-service: timeout connecting to fraud-check-api (attempt 2/3)
[14:15] ERROR payment-service: timeout connecting to fraud-check-api (attempt 3/3)
[14:15] ERROR payment-service: transaction failed — fraud_check_unavailable
[14:16–14:34] ERROR payment-service: [897 occurrences] fraud_check_unavailable
[14:35] INFO  payment-service: fraud-check-api connection restored
[14:35] INFO  payment-service: error rate normalized
```

```tool_call
tool: run_query
input: {
  "log_data": "logs_14h00_15h00",
  "pattern": "fraud-check-api response times over time"
}
```

```tool_result
{
  "fraud_check_api_p99_latency_ms": {
    "14:00": 145,
    "14:10": 380,
    "14:14": 2800,
    "14:15": "timeout (>3000ms)",
    "14:35": 160
  },
  "correlation": "Degradação da fraud-check-api começou às 14:10, atingiu timeout às 14:15. Rollback do payment-service não resolveu pois a causa era externa."
}
```

```tool_result
[Sub-agente Log Analyzer — resultado final para o Orquestrador]
{
  "root_cause_hypothesis": "Falha na fraud-check-api (dependência externa). Latência aumentou de 145ms para timeout (>3000ms) entre 14:10 e 14:15. O payment-service não tinha circuit breaker configurado, propagando a falha para todos os pagamentos.",
  "affected_components": ["payment-service", "fraud-check-api"],
  "timeline": [
    "14:10 — fraud-check-api começa a degradar (p99: 380ms)",
    "14:15 — fraud-check-api atinge timeout completo",
    "14:15 — payment-service inicia cascade de erros (897 transações afetadas)",
    "14:15 — rollback executado (não resolveu — causa era externa)",
    "14:35 — fraud-check-api recuperada, erros normalizados"
  ],
  "severity": "SEV-2",
  "recommendation": "Implementar circuit breaker no payment-service para a chamada à fraud-check-api. Considerar modo degradado (aprovação condicional) quando o serviço externo estiver indisponível."
}
```

---

### Passo 5 — REASONING: Orquestrador recebe análise e decide próximo passo

**Quem age:** Agente Orquestrador (raciocínio interno)
**O que acontece:** O orquestrador recebe a análise estruturada do log-analyzer, confirma que a causa raiz está clara e decide delegar a criação do post-mortem ao report-writer.

```thinking
Causa raiz confirmada: fraud-check-api como dependência externa sem circuit breaker.
897 transações afetadas, duração de ~20 minutos. SEV-2.

A recomendação do log-analyzer (circuit breaker + modo degradado) é sólida.
Agora vou delegar ao report-writer para criar o post-mortem no Confluence.

Vou passar toda a análise estruturada — o report-writer não tem acesso ao log-analyzer.
```

---

### Passo 6 — TOOL CALL (local): Delegação para sub-agente de documentação

**Quem age:** Orquestrador → Tool `delegate_to_agent`
**O que acontece:** O orquestrador passa a análise completa para o report-writer criar o post-mortem no Confluence.

```tool_call
tool: delegate_to_agent
input: {
  "agent_name": "report-writer",
  "task_context": {
    "incident_title": "SEV-2: payment-service — 40% error rate (2025-03-19)",
    "incident_summary": "Falha em cascata no payment-service causada por timeout na fraud-check-api. 897 transações afetadas entre 14:15 e 14:35.",
    "analysis": {
      "root_cause": "fraud-check-api sem circuit breaker no payment-service",
      "timeline": ["14:10 — degradação", "14:15 — timeout + cascade", "14:35 — recuperação"],
      "affected_components": ["payment-service", "fraud-check-api"],
      "severity": "SEV-2"
    },
    "recommendations": [
      "Implementar circuit breaker (padrão: 3 falhas em 10s → abrir circuito por 30s)",
      "Criar modo degradado: aprovação condicional quando fraud-check indisponível",
      "Adicionar alerta dedicado para latência da fraud-check-api (threshold: >500ms)"
    ],
    "task": "Crie um post-mortem no Confluence usando o template padrão. Espaço: ENG. Título: SEV-2: payment-service 2025-03-19."
  }
}
```

---

### Passo 7 — SUB-AGENTE (Report Writer): Criação do post-mortem via MCP

**Quem age:** Sub-agente Report Writer (execução interna com MCP)
**O que acontece:** O report-writer usa o servidor MCP do Confluence para criar a página de post-mortem com o conteúdo estruturado recebido do orquestrador.

```thinking
[INTERNO — Sub-agente Report Writer]
Recebi análise completa. Vou estruturar o post-mortem usando o template padrão e criar
a página no Confluence via MCP.
```

```mcp_call
server: confluence-mcp
tool: confluence__create_page
input: {
  "space": "ENG",
  "title": "SEV-2: payment-service — 40% error rate (2025-03-19)",
  "body": "## Summary\nIncidente de severidade 2 no payment-service em 19/03/2025. Taxa de erro atingiu 40% por ~20 minutos (897 transações afetadas) devido a falha em cascata originada na fraud-check-api.\n\n## Timeline\n- 14:10 — fraud-check-api começa a degradar (p99: 380ms)\n- 14:15 — fraud-check-api atinge timeout; payment-service inicia cascade de erros\n- 14:15 — Rollback executado (não resolveu — causa era externa)\n- 14:35 — fraud-check-api recuperada; erros normalizados\n\n## Root Cause\nO payment-service não possui circuit breaker para chamadas à fraud-check-api. Quando esta dependência externa atingiu timeout (>3000ms), todos os pagamentos foram rejeitados sem fallback.\n\n## Impact\n- 897 transações de pagamento falhadas\n- Duração: ~20 minutos\n- Severidade: SEV-2\n\n## Action Items\n| Ação | Responsável | Prazo |\n|------|-------------|-------|\n| Implementar circuit breaker na chamada à fraud-check-api | Time Payments | 26/03 |\n| Criar modo degradado (aprovação condicional) | Time Payments | 02/04 |\n| Adicionar alerta de latência fraud-check-api (>500ms) | Time SRE | 24/03 |"
}
```

```mcp_result
{
  "status": "created",
  "page_id": "CONF-98423",
  "url": "https://confluence.empresa.com/display/ENG/SEV-2-payment-service-20250319",
  "space": "ENG",
  "title": "SEV-2: payment-service — 40% error rate (2025-03-19)"
}
```

```tool_result
[Sub-agente Report Writer — resultado final para o Orquestrador]
{
  "status": "post_mortem_created",
  "confluence_url": "https://confluence.empresa.com/display/ENG/SEV-2-payment-service-20250319",
  "page_id": "CONF-98423"
}
```

---

### Passo 8 — MODELO: Resposta consolidada ao usuário

**Quem age:** Agente Orquestrador
**O que acontece:** O orquestrador sintetiza os resultados dos dois sub-agentes e entrega ao usuário uma resposta clara com causa raiz, impacto e link para o post-mortem.

```assistant
✅ **Incidente investigado e documentado.** Aqui está o resumo completo:

---

**🔍 Causa Raiz**
Falha na **fraud-check-api** (dependência externa). A latência desta API aumentou de 145ms para timeout (>3s) entre 14:10 e 14:15. O `payment-service` **não possui circuit breaker** para essa chamada — o que propagou a falha para 100% das transações em processamento.

> Por isso o rollback não resolveu imediatamente: a causa era externa ao serviço que foi revertido.

---

**📊 Impacto**
- **Transações afetadas:** 897
- **Janela de impacto:** 14:15 → 14:35 (~20 minutos)
- **Severidade:** SEV-2

---

**⏱️ Timeline**
| Horário | Evento |
|---------|--------|
| 14:10 | fraud-check-api começa a degradar |
| 14:15 | Timeout completo → cascade de erros |
| 14:15 | Rollback executado (sem efeito) |
| 14:35 | fraud-check-api recuperada |

---

**🛠️ Action Items (já no post-mortem)**
1. Circuit breaker na chamada à fraud-check-api — **Time Payments, até 26/03**
2. Modo degradado (aprovação condicional) — **Time Payments, até 02/04**
3. Alerta de latência fraud-check-api (>500ms) — **Time SRE, até 24/03**

---

**📄 Post-mortem criado:**
🔗 [SEV-2: payment-service — 40% error rate (2025-03-19)](https://confluence.empresa.com/display/ENG/SEV-2-payment-service-20250319)
```

---

## 📊 Resumo do Fluxo

| Passo | Tipo | Agente | Descrição resumida |
|-------|------|--------|--------------------|
| 1 | USUÁRIO | Usuário | Reporta incidente no payment-service com 40% error rate |
| 2 | REASONING | Orquestrador | Planeja delegação: log-analyzer → report-writer |
| 3 | TOOL CALL | Orquestrador → `delegate_to_agent` | Delega análise de logs ao sub-agente especializado |
| 4 | EXECUÇÃO | Sub-agente Log Analyzer | Busca logs, roda queries, retorna análise estruturada com causa raiz |
| 5 | REASONING | Orquestrador | Recebe análise, confirma causa raiz, decide criar post-mortem |
| 6 | TOOL CALL | Orquestrador → `delegate_to_agent` | Delega documentação ao sub-agente report-writer |
| 7 | EXECUÇÃO (MCP) | Sub-agente Report Writer | Cria post-mortem no Confluence via MCP, retorna URL |
| 8 | MODELO | Orquestrador | Sintetiza resultados e entrega resposta consolidada ao usuário |

---

## 💡 Conceitos Ilustrados

- **Arquitetura multi-agente:** orquestrador coordena sub-agentes especializados — cada um tem system prompt, ferramentas e responsabilidade distintos
- **Delegação com contexto completo:** sub-agentes não têm memória compartilhada — o orquestrador precisa passar todo o contexto relevante em cada delegação (`task_context`)
- **Especialização de agentes:** log-analyzer tem tools de análise técnica; report-writer tem acesso ao MCP de documentação — separação de responsabilidades
- **Encadeamento dependente:** o report-writer só é chamado *depois* que o log-analyzer retorna — o orquestrador sequencia as delegações com base nos resultados
- **MCP em sub-agente:** a integração com Confluence acontece dentro do sub-agente report-writer, não no orquestrador — o MCP é uma capacidade do agente especializado
- **Síntese pelo orquestrador:** o usuário final recebe uma resposta unificada do orquestrador — ele não precisa saber que dois sub-agentes foram envolvidos
- **Ponte para riscos (próxima aula):** este fluxo ilustra naturalmente riscos como prompt injection entre agentes, excesso de privilégio no sub-agente e ausência de human-in-the-loop antes de criar documentação
