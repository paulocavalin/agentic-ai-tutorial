# Fluxo: Agente com Humano no Loop (Human-in-the-Loop)

## Visão Geral

Este fluxo demonstra um **Agente de Infraestrutura** que executa automações em um ambiente cloud.  
Antes de qualquer ação **destrutiva ou irreversível**, o agente **pausa, resume o contexto e aguarda aprovação humana**.

```
Usuário/Operador                  Agente                    Sistema Cloud
      │                              │                             │
      │  "Limpa backups antigos e    │                             │
      │   libera espaço no bucket"   │                             │                           │──────────────────────────►│                             │
      │                              │ list_backups()              │
      │                              │────────────────────────────►│
      │                              │◄────────────────────────────│
      │                              │ 12 arquivos encontrados     │
      │                              │                             │
      │                              │ [Ação destrutiva detectada] │
      │                              │ delete_files() requer       │
      │                              │ aprovação humana            │
      │◄─────────────────────────────│                             │
      │  [CHECKPOINT DE APROVAÇÃO]   │                             │
      │  Contexto + risco mostrado   │                             │
      │                              │                             │
      │  Humano decide: aprovar ou   │                             │
      │  rejeitar                    │                             │
      │──────────────────────────►│                             │
      │  (aprovação: sim)            │                             │
      │                              │ delete_files()              │
      │                              │────────────────────────────►│
      │                              │◄────────────────────────────│
      │                              │ 12 arquivos deletados       │
      │                              │ 4.2 GB liberados            │
      │◄─────────────────────────────│                             │
      │  Relatório final             │                             │
```

**Padrão:** Approval Checkpoint — o agente não age por conta própria em operações de alto risco.

---

## Tipos de Ação

| Tipo | Exemplos | Requer Aprovação |
|------|----------|-----------------|
| **Read-only** | listar arquivos, verificar status, consultar logs | ❌ Não |
| **Write não-destrutiva** | criar arquivo, adicionar tag, enviar alerta | ❌ Não |
| **Write destrutiva** | deletar arquivo, derrubar serviço, modificar permissões | ✅ **Sim** |
| **Irreversível** | apagar banco, revogar credenciais, destruir recurso cloud | ✅ **Sim + Confirmação** |

---

## System Prompt do Agente

```
Você é um agente de automação de infraestrutura cloud.

Você tem acesso a ferramentas para listar, inspecionar e modificar recursos.

REGRA CRÍTICA: Antes de executar qualquer ferramenta marcada como [DESTRUTIVA],
você deve PARAR e emitir um CHECKPOINT no formato:

---APROVAÇÃO NECESSÁRIA---
Ação: <nome da ferramenta>
Argumentos: <parâmetros JSON>
Impacto esperado: <o que será modificado/deletado>
Risco: <consequências se executado incorretamente>
Reversível: Sim / Não
---FIM DO CHECKPOINT---

Aguarde a resposta do operador antes de prosseguir.
Se aprovado, execute a ação e relate o resultado.
Se rejeitado, explore alternativas ou encerre a tarefa.
```

---

## Cenário A: Aprovação concedida

**Objetivo:** Limpar backups com mais de 90 dias para liberar espaço.

### Passo 1 — Usuário envia a solicitação

**Quem age:** Usuário/Operador  

```
Usuário → Agente
role: "user"

"Preciso liberar espaço no bucket s3://prod-backups. 
 Delete backups com mais de 90 dias. Temos um custo alto de storage."
```

### Passo 2 — Agente planeja e executa ação de leitura

**Quem age:** Agente (planejamento interno + chamada de ferramenta)  
**O que acontece:** O agente analisa a solicitação e executa a ferramenta de listagem (read-only → sem checkpoint).

```
Agente → LLM (raciocínio interno)
role: "assistant"
<thinking>
A solicitação envolve deletar arquivos. Antes de deletar, preciso:
1. Listar os arquivos para saber o que será afetado [SAFE — read-only]
2. Filtrar por data > 90 dias
3. Apresentar checkpoint de aprovação ANTES de deletar [OBRIGATÓRIO]
</thinking>

Chamada de ferramenta:
{
  "tool": "list_backups",
  "arguments": {
    "bucket": "s3://prod-backups",
    "older_than_days": 90
  }
}
```

### Passo 3 — Resultado da ferramenta (leitura)

**Quem age:** Sistema (retorno da ferramenta)  

```
Sistema → Agente
role: "tool"

{
  "files": [
    {"name": "backup-2024-10-01.tar.gz", "size_gb": 0.8, "age_days": 102},
    {"name": "backup-2024-10-15.tar.gz", "size_gb": 1.1, "age_days": 88},
    {"name": "backup-2024-11-01.tar.gz", "size_gb": 0.9, "age_days": 71},
    // ... mais 9 arquivos
  ],
  "total_files": 12,
  "total_size_gb": 4.2,
  "oldest_file_days": 102
}
```

> **Nota:** Dos 12 arquivos retornados, apenas os com `age_days > 90` serão candidatos à exclusão.

### Passo 4 — Agente detecta ação destrutiva e emite checkpoint

**Quem age:** Agente  
**O que acontece:** O agente obedece à regra do system prompt e **para antes de deletar**.

```
Agente → Usuário
role: "assistant"

Encontrei 8 arquivos elegíveis para exclusão (> 90 dias).

---APROVAÇÃO NECESSÁRIA---
Ação: delete_files
Argumentos: {
  "bucket": "s3://prod-backups",
  "files": [
    "backup-2024-10-01.tar.gz",
    "backup-2024-10-08.tar.gz",
    ... (8 arquivos)
  ]
}
Impacto esperado: Remoção de 8 arquivos de backup com mais de 90 dias.
                  Espaço liberado: aproximadamente 3.1 GB.
                  Arquivos mais recentes (< 90 dias) não serão afetados.
Risco: Backups deletados não poderão ser recuperados.
       Confirme que nenhum desses backups é necessário para auditoria ou recuperação.
Reversível: Não
---FIM DO CHECKPOINT---

Aguardando sua aprovação para prosseguir.
```

> 💡 **Conceito-chave:** O agente fornece **contexto suficiente para uma decisão informada** — sem forçar o humano a re-inspecionar o bucket manualmente.

### Passo 5 — Humano decide: APROVAR

**Quem age:** Humano/Operador  

```
Usuário → Agente
role: "user"

"Aprovado. Pode deletar."
```

### Passo 6 — Agente executa a ação destrutiva

**Quem age:** Agente (executa a ferramenta aprovada)  

```
Agente → Sistema
role: "assistant"

{
  "tool": "delete_files",
  "arguments": {
    "bucket": "s3://prod-backups",
    "files": ["backup-2024-10-01.tar.gz", ... (8 arquivos)]
  }
}
```

### Passo 7 — Resultado e relatório final

**Quem age:** Agente (sintetiza resultado)  

```
Agente → Usuário
role: "assistant"

✅ Operação concluída com sucesso.

Resumo da limpeza:
- Arquivos deletados: 8
- Espaço liberado: 3.1 GB
- Bucket atual: 1.1 GB (4 arquivos restantes, todos < 90 dias)
- Estimativa de economia mensal: ~$4.80 (@ $0.023/GB/mês S3 Standard)

Os 4 backups recentes foram preservados conforme a política de retenção.
```

---

## Cenário B: Aprovação negada → Alternativa sugerida

### Situação diferente — Operador recusa a exclusão

Após ver o checkpoint no **Passo 4**, o operador descobre que um dos backups tem relevância para uma auditoria.

```
Usuário → Agente
role: "user"

"Não aprove ainda. O backup de 2024-10-01 pode ser necessário para auditoria de Q4.
 Existe uma alternativa?"
```

**Agente responde com plano alternativo:**

```
Agente → Usuário
role: "assistant"

Entendido. Operação de exclusão cancelada.

Alternativas disponíveis:

1. Mover para Glacier (arquivamento frio):
   - Custo: ~$0.004/GB/mês (vs $0.023/GB atual)
   - Acesso: disponível em 3-5 horas quando necessário
   - Reversível: Sim (restauração com custo)

2. Deletar apenas os 7 arquivos sem relevância de auditoria:
   - Espaço liberado: 2.3 GB
   - backup-2024-10-01.tar.gz preservado

3. Adicionar tag "audit-hold" ao arquivo e deletar os demais:
   - Previne exclusão acidental futura
   - Compatível com políticas de retenção obrigatória

Qual alternativa prefere?
```

> 💡 **Conceito-chave:** O agente **não desiste** da tarefa — ele propõe caminhos seguros dentro dos limites definidos pelo humano.

---

## Cenário C: Ação de risco máximo (dupla confirmação)

**Situação:** Agente detecta que a solicitação envolve destruição de recurso de banco de dados de produção.

```
Usuário → Agente
role: "user"

"O banco de testes antigo na RDS está gerando custo. Pode destruir?"
```

**Agente faz checkpoint de dois estágios:**

```
Agente → Usuário
role: "assistant"

---APROVAÇÃO NECESSÁRIA [RISCO CRÍTICO]---
Ação: destroy_rds_instance
Argumentos: {
  "instance_id": "rds-legacy-tests-2023",
  "region": "us-east-1"
}
Impacto esperado: Destruição permanente da instância RDS.
                  Todos os dados serão apagados.
                  Snapshots automáticos serão retidos por 7 dias (padrão AWS).
Risco: IRREVERSÍVEL após o período de retenção de snapshots.
       Confirme que não há aplicações apontando para este endpoint.
       Confirme que um snapshot manual foi criado como backup.
Reversível: Não (apenas restauração via snapshot nos próximos 7 dias)

⚠  Para confirmar, responda exatamente: DESTRUIR rds-legacy-tests-2023
---FIM DO CHECKPOINT---
```

> 💡 **Conceito-chave:** Para ações de **risco máximo**, o agente pode exigir uma **confirmação explícita por palavra-chave** — similar ao padrão de confirmação do CLI da AWS (`aws rds delete-db-instance --skip-final-snapshot`).

---

## Resumo do Fluxo

| Passo | Agente age | Humano age | Ferramenta |
|-------|-----------|-----------|-----------|
| 1 | Recebe solicitação | Envia pedido | — |
| 2 | Planeja, classifica ações | — | `list_backups` (leitura) |
| 3 | Recebe lista de arquivos | — | — |
| 4 | **Emite checkpoint** | — | — |
| 5 | Aguarda | **Aprova ou rejeita** | — |
| 6 | Executa (se aprovado) | — | `delete_files` (destrutiva) |
| 7 | Relata resultado | Confirma | — |

---

## Conceitos Ilustrados

| Conceito | Onde aparece |
|----------|-------------|
| **Approval Checkpoint** | Passos 4–5: agente para, apresenta contexto estruturado, aguarda |
| **Classificação de risco** | Tabela de tipos de ação: read-only vs. destrutivo vs. irreversível |
| **Contexto para decisão** | Checkpoint inclui impacto, risco e reversibilidade — não só "ok/não ok" |
| **Graceful rejection** | Cenário B: agente propõe alternativas após negativa |
| **Double confirmation** | Cenário C: confirmação por palavra-chave para risco máximo |
| **Tool transparency** | Os argumentos exatos são exibidos ao humano antes da execução |
| **Autonomia calibrada** | Ações seguras (leitura) são executadas sem interrupção; risco dispara pausa |

### Por que HITL importa em produção

```
Sem HITL:
  Usuário: "Limpa os logs antigos"
  Agente: [deleta /var/log/prod/ inteiro] ← interpretação errônea, sem reversão

Com HITL:
  Usuário: "Limpa os logs antigos"
  Agente: [lista logs] → [emite checkpoint com escopo exato] → [aguarda aprovação]
  Operador: "Só os logs de acesso, não os de erro"
  Agente: [deleta apenas access.log.*] ✓
```

O checkpoint não é um obstáculo — é o **contrato de confiança** entre o agente e o operador.
