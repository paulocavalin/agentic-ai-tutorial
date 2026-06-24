# 🤖 Simulação de Fluxo Agêntico — Agente Corporativo (CRM + Email via MCP)

---

## 🗺️ Visão Geral do Sistema

**Cenário:** Um agente de vendas B2B que auxilia um executivo de contas. Ao receber uma solicitação, o agente consulta o CRM para obter contexto do cliente, analisa o histórico, e envia um email personalizado de follow-up — tudo via servidores MCP externos.

```
Usuário (executivo de contas)
  │
  ▼
Modelo (LLM)
  │
  ├─► [REASONING] Identifica que precisa de contexto do cliente
  │
  ├─► MCP: salesforce__get_contact("Empresa ABC") ──► dados do contato
  │
  ├─► MCP: salesforce__get_opportunity("OPP-2847") ──► histórico da oportunidade
  │
  ├─► [REASONING] Analisa situação e decide ação
  │
  ├─► [REASONING] Rascunha email personalizado
  │
  ├─► MCP: gmail__send_email(...) ──► email enviado
  │
  └─► Resposta ao usuário confirmando ações realizadas
```

**Componentes envolvidos:**
- **Modelo:** LLM com acesso a servidores MCP
- **MCP Server 1:** Salesforce CRM — consulta contatos e oportunidades
- **MCP Server 2:** Gmail — redação e envio de emails
- **Protocolo:** Model Context Protocol (MCP) para integração com sistemas externos

---

## ⚙️ System Prompt

```system
Você é um assistente de vendas B2B especializado em relacionamento com clientes.
Você tem acesso a dois sistemas externos via MCP:

1. Salesforce CRM (servidor: salesforce-mcp)
   - salesforce__get_contact(name): retorna dados do contato e empresa
   - salesforce__get_opportunity(id): retorna detalhes e histórico de uma oportunidade
   - salesforce__update_opportunity(id, fields): atualiza campos de uma oportunidade

2. Gmail (servidor: gmail-mcp)
   - gmail__send_email(to, subject, body): envia um email
   - gmail__get_thread(thread_id): recupera thread de email existente

Instruções de comportamento:
- Sempre consulte o CRM antes de escrever qualquer comunicação ao cliente.
- Personalize emails com base no histórico real do CRM — nunca invente informações.
- Antes de enviar um email, apresente o rascunho ao usuário para aprovação, a menos que ele peça envio direto.
- Após enviar, atualize o CRM com um registro da interação.
- Tom: profissional, consultivo, orientado a valor — nunca agressivo ou genérico.
```

---

## 🔄 Fluxo de Interação (passo a passo)

---

### Passo 1 — USUÁRIO: Solicitação de follow-up

**Quem age:** Usuário
**O que acontece:** O executivo de contas pede ao agente para fazer o follow-up com um cliente que está em fase de decisão. Ele inclui o ID da oportunidade como referência.

```user
Preciso fazer um follow-up com a Empresa ABC — eles estão na fase de proposta há 2 semanas
e a oportunidade é OPP-2847. Manda um email para o contato principal lembrando do valor
que discutimos e perguntando se há bloqueios para avançar. Pode enviar direto.
```

---

### Passo 2 — REASONING: Planejamento das ações necessárias

**Quem age:** Modelo (raciocínio interno)
**O que acontece:** O modelo interpreta a solicitação. Identifica que precisa de informações do CRM antes de escrever qualquer email — não pode inventar dados do cliente.

```thinking
O usuário quer um follow-up para OPP-2847 / Empresa ABC.
Ele autorizou envio direto — não preciso pedir aprovação prévia do rascunho.

Minha sequência de ações:
1. Buscar dados do contato principal da Empresa ABC no Salesforce
2. Buscar detalhes da oportunidade OPP-2847 (valor, proposta, histórico, último contato)
3. Com esses dados, redigir um email personalizado
4. Enviar via Gmail
5. Atualizar o CRM com registro da interação

Vou começar buscando o contato e a oportunidade em paralelo — ambos são do Salesforce.
```

---

### Passo 3 — TOOL CALL (MCP): Consulta ao contato no CRM

**Quem age:** Modelo → MCP Server `salesforce-mcp`
**O que acontece:** O modelo consulta o Salesforce para obter os dados do contato principal da Empresa ABC. O servidor MCP acessa o CRM real e retorna os dados estruturados.

```mcp_call
server: salesforce-mcp
tool: salesforce__get_contact
input: {
  "name": "Empresa ABC"
}
```

```mcp_result
{
  "contact": {
    "name": "Fernanda Oliveira",
    "title": "Diretora de Operações",
    "email": "fernanda.oliveira@empresaabc.com.br",
    "phone": "+55 11 9xxxx-xxxx",
    "last_activity": "2025-03-01",
    "preferred_channel": "email"
  },
  "account": {
    "name": "Empresa ABC Logística",
    "industry": "Logística e Transporte",
    "employees": 1200,
    "account_manager": "Rafael Souza"
  }
}
```

---

### Passo 4 — TOOL CALL (MCP): Consulta à oportunidade no CRM

**Quem age:** Modelo → MCP Server `salesforce-mcp`
**O que acontece:** O modelo busca os detalhes completos da oportunidade — valor, estágio, proposta enviada e histórico de interações — para personalizar o email com informações reais.

```mcp_call
server: salesforce-mcp
tool: salesforce__get_opportunity
input: {
  "id": "OPP-2847"
}
```

```mcp_result
{
  "opportunity": {
    "id": "OPP-2847",
    "name": "Plataforma de Visibilidade de Frota — Empresa ABC",
    "stage": "Proposal/Price Quote",
    "amount": 480000,
    "currency": "BRL",
    "close_date": "2025-04-30",
    "probability": 60,
    "proposal_sent_date": "2025-03-05",
    "key_value_props": [
      "Redução de 22% em custos operacionais de frota",
      "Integração nativa com sistema TMS existente",
      "SLA de implementação: 45 dias"
    ],
    "last_interaction": {
      "date": "2025-03-05",
      "type": "email",
      "summary": "Proposta técnica e comercial enviada. Fernanda confirmou recebimento."
    },
    "next_steps": "Aguardando feedback interno sobre aprovação orçamentária"
  }
}
```

---

### Passo 5 — REASONING: Análise e redação do email

**Quem age:** Modelo (raciocínio interno)
**O que acontece:** Com os dados reais do CRM, o modelo analisa a situação e redige um email personalizado. Considera o contexto (proposta há 2 semanas, bloqueio provável é aprovação orçamentária) para ajustar o tom e o conteúdo.

```thinking
Tenho tudo que preciso para escrever um email relevante:
- Contato: Fernanda Oliveira, Diretora de Operações
- Proposta enviada em 05/03, valor R$480k, estágio: aguardando aprovação orçamentária
- Valores discutidos: 22% redução de custo, integração TMS, 45 dias de implementação

O email deve:
1. Referenciar a proposta enviada (não ser genérico)
2. Reforçar o valor principal (22% redução de custos — dado concreto)
3. Reconhecer que provavelmente há processo interno (não pressionar, mas perguntar sobre bloqueios)
4. Ter um CTA claro: propor uma call curta para tirar dúvidas

Tom: consultivo, não de vendas agressivas. Fernanda é Diretora — nível sênior, prefere objetividade.
Assunto deve ser específico, não genérico.
```

---

### Passo 6 — TOOL CALL (MCP): Envio do email via Gmail

**Quem age:** Modelo → MCP Server `gmail-mcp`
**O que acontece:** O modelo envia o email personalizado para Fernanda através do servidor MCP do Gmail. O email contém referências diretas à proposta e aos valores discutidos.

```mcp_call
server: gmail-mcp
tool: gmail__send_email
input: {
  "to": "fernanda.oliveira@empresaabc.com.br",
  "subject": "Plataforma de Visibilidade de Frota — próximos passos | OPP-2847",
  "body": "Olá Fernanda,\n\nEspero que esteja bem. Queria fazer um acompanhamento da proposta que enviamos em 5 de março referente à Plataforma de Visibilidade de Frota para a Empresa ABC Logística.\n\nSei que processos de aprovação têm seu tempo, e quero garantir que tenhamos dado a você todo o material necessário para facilitar a decisão internamente. Só para recapitular os pontos centrais da proposta:\n\n• Redução estimada de 22% nos custos operacionais de frota\n• Integração nativa com o TMS que vocês já utilizam — sem necessidade de substituição\n• Prazo de implementação: 45 dias após assinatura\n\nSe houver qualquer ponto técnico, comercial ou de compliance que esteja pendente, adoraria ajudar a resolver. Você teria 20 minutos esta semana ou na próxima para uma call rápida?\n\nAtenciosamente,\nRafael Souza\nExecutivo de Contas Sênior"
}
```

```mcp_result
{
  "status": "sent",
  "message_id": "msg_abc987xyz",
  "timestamp": "2025-03-19T14:32:07-03:00",
  "to": "fernanda.oliveira@empresaabc.com.br"
}
```

---

### Passo 7 — TOOL CALL (MCP): Atualização do CRM

**Quem age:** Modelo → MCP Server `salesforce-mcp`
**O que acontece:** Após o envio bem-sucedido, o modelo atualiza automaticamente o registro da oportunidade no CRM para manter o histórico de interações completo.

```mcp_call
server: salesforce-mcp
tool: salesforce__update_opportunity
input: {
  "id": "OPP-2847",
  "fields": {
    "last_activity_date": "2025-03-19",
    "last_activity_type": "Email",
    "last_activity_note": "Follow-up automático enviado via agente IA. Reforço dos value props (22% redução custo, integração TMS, SLA 45d). CTA: call de 20min para resolver bloqueios.",
    "next_step": "Aguardar resposta de Fernanda — follow-up manual em 5 dias úteis se não houver retorno."
  }
}
```

```mcp_result
{
  "status": "updated",
  "opportunity_id": "OPP-2847",
  "fields_updated": ["last_activity_date", "last_activity_type", "last_activity_note", "next_step"]
}
```

---

### Passo 8 — MODELO: Confirmação ao usuário

**Quem age:** Modelo
**O que acontece:** O modelo confirma todas as ações realizadas para o executivo de contas, com um resumo claro do que foi feito e o próximo passo sugerido.

```assistant
✅ **Follow-up realizado com sucesso.** Aqui está o resumo do que foi feito:

**📧 Email enviado**
- **Para:** Fernanda Oliveira (fernanda.oliveira@empresaabc.com.br)
- **Assunto:** Plataforma de Visibilidade de Frota — próximos passos | OPP-2847
- **Conteúdo:** Reforçou os 3 value props principais (22% redução de custo, integração TMS, SLA 45 dias) e propôs uma call de 20 minutos para resolver possíveis bloqueios.

**🗃️ CRM atualizado**
- Oportunidade OPP-2847 atualizada com registro da interação de hoje.
- Next step definido: follow-up manual em 5 dias úteis caso não haja resposta.

**📋 Contexto da oportunidade**
- Valor: R$ 480.000 | Probabilidade: 60% | Fechamento previsto: 30/04
- Última interação anterior: 05/03 (envio da proposta)

Vou te lembrar em **24/03** se Fernanda não responder até lá. Deseja ajustar algo no email ou no registro do CRM?
```

---

## 📊 Resumo do Fluxo

| Passo | Tipo | Agente | Descrição resumida |
|-------|------|--------|--------------------|
| 1 | USUÁRIO | Usuário | Solicita follow-up para Empresa ABC / OPP-2847, envio direto autorizado |
| 2 | REASONING | Modelo | Planeja sequência: buscar CRM → redigir email → enviar → atualizar CRM |
| 3 | TOOL CALL (MCP) | Modelo → Salesforce | Busca dados do contato principal (Fernanda Oliveira) |
| 4 | TOOL CALL (MCP) | Modelo → Salesforce | Busca detalhes da oportunidade: valor, proposta, histórico |
| 5 | REASONING | Modelo | Analisa contexto e redige email personalizado com dados reais do CRM |
| 6 | TOOL CALL (MCP) | Modelo → Gmail | Envia email personalizado com referências à proposta |
| 7 | TOOL CALL (MCP) | Modelo → Salesforce | Atualiza CRM com registro da interação realizada |
| 8 | MODELO | Modelo | Confirma ações ao usuário com resumo e próximo passo sugerido |

---

## 💡 Conceitos Ilustrados

- **MCP (Model Context Protocol):** o agente se conecta a sistemas externos reais (Salesforce, Gmail) via servidores MCP — sem necessidade de integrações customizadas para cada sistema
- **Grounding em dados reais:** o email é redigido *depois* de consultar o CRM — o agente nunca inventa informações sobre o cliente
- **Sequência de ações dependentes:** cada passo depende do resultado do anterior (consulta → análise → ação → atualização)
- **Autorização explícita no prompt:** o usuário disse "pode enviar direto" — o agente respeitou essa instrução e não pediu aprovação adicional
- **Fechamento do loop:** após a ação principal (email), o agente atualiza o sistema de origem (CRM) — comportamento esperado em fluxos corporativos reais
- **Human-in-the-loop condicional:** o system prompt exige aprovação *a menos que* o usuário peça envio direto — ilustra como controlar autonomia via configuração
