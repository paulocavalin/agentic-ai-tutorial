# Fluxo: Agente de Design Computacional (Pipeline Completo)

## Visão Geral

Este fluxo demonstra um **Agente de Design Computacional** que transforma uma descrição em linguagem natural em um projeto 3D completo e pronto para impressão, com sourcing de peças.

```
Usuário                    Agente                     Ferramentas
  │                           │                            │
  │  "Preciso de uma caixa    │                            │
  │   para Arduino com        │                            │
  │   ventilação e USB"       │                            │
  │──────────────────────────►│                            │
  │                           │ create_design_brief()      │
  │                           │───────────────────────────►│
  │                           │◄───────────────────────────│
  │                           │ {project_name, dims, ...}  │
  │                           │                            │
  │                           │ generate_openscad_code()   │
  │                           │───────────────────────────►│
  │                           │◄───────────────────────────│
  │                           │ // OpenSCAD parametric...  │
  │                           │                            │
  │                           │ render_model()             │
  │                           │───────────────────────────►│ ← OpenSCAD CLI
  │                           │◄───────────────────────────│
  │                           │ preview.png + model.stl    │
  │                           │                            │
  │                           │ optimize_design()          │
  │                           │───────────────────────────►│
  │                           │◄───────────────────────────│
  │                           │ {issues, optimized_code}   │
  │                           │                            │
  │                           │ suggest_print_settings()   │
  │                           │───────────────────────────►│
  │                           │◄───────────────────────────│
  │                           │ {layer_height, infill...}  │
  │                           │                            │
  │                           │ source_parts()             │
  │                           │───────────────────────────►│ ← Catálogo
  │                           │◄───────────────────────────│
  │                           │ BOM + preços estimados     │
  │◄──────────────────────────│                            │
  │  Projeto completo:        │                            │
  │  .scad + .stl + BOM       │                            │
```

**Padrão:** Agente como Orquestrador de Pipeline — cada etapa é uma chamada de ferramenta estruturada que produz um artefato concreto.

---

## Arquitetura: Por que OpenSCAD?

| Critério | OpenSCAD | CadQuery (Python) | Blender |
|----------|----------|-------------------|---------|
| Sintaxe para LLM gerar | ✅ Simples e declarativa | ⚠ Python complexo | ❌ API extensa |
| Export STL direto | ✅ CLI nativo | ✅ Python | ✅ Mas verboso |
| Paramétrico | ✅ Por design | ✅ Muito poderoso | ⚠ Limitado |
| Curva de aprendizado | ✅ Baixa | ⚠ Média | ❌ Alta |
| Ideal para ensino | ✅ | ⚠ | ❌ |

```openscad
// OpenSCAD: declarativo, paramétrico, direto
wall_t = 2;         // variável de parede
screw_d = 3.2;      // furo para parafuso M3

module body() {
    difference() {
        cube([80, 60, 40]);
        translate([wall_t, wall_t, wall_t])
            cube([80 - wall_t*2, 60 - wall_t*2, 41]);
    }
}
```

---

## System Prompt do Agente

```
Você é um engenheiro de design de produtos especializado em fabricação digital.

Você orquestra um pipeline de design de 6 etapas. Para cada etapa, você chama
a ferramenta correspondente e usa o output como input da próxima.

REGRAS:
1. Chame as ferramentas na ordem exata: brief → scad → render → optimize → settings → bom
2. Cada ferramenta retorna um artefato estruturado. Use-o como entrada da próxima etapa.
3. O código OpenSCAD gerado deve ser funcional e imprimível — sem placeholders.
4. Se render_model() falhar (OpenSCAD não instalado), continue o pipeline com o código.
5. A otimização deve melhorar o código, não reescrever do zero.
```

---

## Etapa 1 — Design Brief

**O que acontece:** O agente extrai parâmetros estruturados da descrição em linguagem natural.

**Entrada:**
```
Usuário → Agente
role: "user"

"Preciso de uma caixa de enclosure para um Arduino Uno com:
 - Furos de acesso para USB-B e jack de energia
 - 4 standoffs M3 para fixar a placa
 - Slots de ventilação em ambos os lados
 - Tampa com encaixe snap-fit
 Tamanho aproximado: 100 × 80 × 40mm. Material: PETG."
```

**Ferramenta chamada:**
```json
{
  "tool": "create_design_brief",
  "arguments": {
    "description": "Caixa para Arduino Uno com ventilação e snap-fit"
  }
}
```

**Resultado estruturado:**
```json
{
  "project_name": "Arduino Uno Enclosure",
  "purpose": "Caixa protetora para Arduino Uno com ventilação passiva e tampa removível",
  "dimensions": {"width_mm": 100, "height_mm": 80, "depth_mm": 40},
  "material": "PETG",
  "features": [
    "Furo USB-B (12x8mm)",
    "Furo jack DC 5.5mm",
    "4x standoffs M3 para placa",
    "Slots de ventilação laterais (1mm × 15mm)",
    "Tampa snap-fit (tolerância 0.2mm)"
  ],
  "constraints": [
    "Placa Arduino Uno: 68.6 × 53.4mm",
    "Standoff height: 5mm",
    "Parede mínima: 2mm para PETG"
  ],
  "hardware": ["4x M3×8mm", "4x M3 heat-set inserts", "Tampa clip"]
}
```

> 💡 **Conceito-chave:** O agente não apenas "entende" a descrição — ele a converte em um schema validado que guia todas as etapas seguintes.

---

## Etapa 2 — Geração do Código OpenSCAD

**O que acontece:** O agente usa o brief estruturado para gerar código CAD paramétrico.

**Ferramenta chamada:**
```json
{
  "tool": "generate_openscad_code",
  "arguments": {
    "brief": { ... }
  }
}
```

**Código gerado (trecho):**
```openscad
// Arduino Uno Enclosure — Gerado por IA
// Parâmetros principais
wall_t     = 2.0;   // espessura da parede (mm)
corner_r   = 3.0;   // raio dos cantos
board_w    = 68.6;  // largura da placa Arduino
board_d    = 53.4;  // profundidade da placa Arduino
standoff_h = 5.0;   // altura dos standoffs
standoff_d = 6.0;   // diâmetro externo dos standoffs
screw_d    = 3.2;   // furo para parafuso M3
box_w      = 100;
box_d      = 80;
box_h      = 40;

// ── Módulo: corpo da caixa ─────────────────────────────────────────
module box_body() {
    difference() {
        // Forma externa com cantos arredondados
        hull() {
            for (x = [corner_r, box_w - corner_r])
            for (y = [corner_r, box_d - corner_r])
                translate([x, y, 0])
                    cylinder(h=box_h, r=corner_r, $fn=32);
        }
        // Cavidade interna
        translate([wall_t, wall_t, wall_t])
            cube([box_w - wall_t*2, box_d - wall_t*2, box_h]);
        // Furo USB-B lateral
        translate([-1, 30, 8])
            cube([wall_t+2, 12, 8]);
        // Furo jack DC
        translate([-1, 50, 10])
            cylinder(h=wall_t+2, d=5.5, $fn=16);
        // Slots de ventilação
        for (i = [0:4])
            translate([20 + i*10, -1, 20])
                cube([1, wall_t+2, 15]);
    }
}

// ── Módulo: standoffs da placa ────────────────────────────────────
module standoffs() {
    for (pos = [[wall_t+2, wall_t+2], [wall_t+2, wall_t+board_d+2],
                [wall_t+board_w+2, wall_t+2], [wall_t+board_w+2, wall_t+board_d+2]])
        translate([pos[0], pos[1], wall_t])
            difference() {
                cylinder(h=standoff_h, d=standoff_d, $fn=16);
                cylinder(h=standoff_h+1, d=screw_d, $fn=16);
            }
}

box_body();
standoffs();
```

> 💡 **Conceito-chave:** A LLM gera **código como artefato de design** — não uma descrição do design, mas o design em si, pronto para compilação.

---

## Etapa 3 — Renderização e Exportação

**O que acontece:** O agente chama o OpenSCAD via linha de comando para produzir previsualizações e o arquivo STL para impressão.

**Ferramenta chamada:**
```json
{
  "tool": "render_model",
  "arguments": {
    "scad_code": "// Arduino Uno Enclosure...",
    "design_id": "a3b7f2c1"
  }
}
```

**Execução interna (subprocesso):**
```bash
# Renderizar PNG
openscad --export-format png --render -o /tmp/cd_pipeline/a3b7f2c1/preview.png model.scad

# Exportar STL
openscad -o /tmp/cd_pipeline/a3b7f2c1/model.stl model.scad
```

**Resultado:**
```json
{
  "png_path": "/tmp/cd_pipeline/a3b7f2c1/preview.png",
  "stl_path": "/tmp/cd_pipeline/a3b7f2c1/model.stl",
  "openscad_available": true,
  "render_error": null
}
```

**Modo degradado (OpenSCAD não instalado):**
```json
{
  "png_path": null,
  "stl_path": null,
  "openscad_available": false,
  "render_error": "OpenSCAD não encontrado. Instale em openscad.org. O código .scad permanece válido."
}
```

> 💡 **Conceito-chave:** O agente integra **ferramentas externas via subprocesso** — o código gerado pelo LLM é compilado por uma ferramenta especializada, não executado diretamente.

---

## Etapa 4 — Otimização para Impressão 3D

**O que acontece:** O agente analisa o código gerado contra regras de printabilidade FDM e produz uma versão melhorada.

**Problemas detectados no exemplo:**
```json
{
  "issues": [
    {
      "severity": "high",
      "description": "Overhang de 90° no furo USB-B sem suporte — imprimirá mal.",
      "fix": "Adicionar chanfro 45° na parte superior do furo ou substituir por abertura chanfrada."
    },
    {
      "severity": "medium",
      "description": "Furo do jack DC usa cylinder sem tolerância de montagem.",
      "fix": "Aumentar diâmetro para 5.7mm (+0.2mm tolerance fit)."
    },
    {
      "severity": "low",
      "description": "Slots de ventilação com 1mm — pode ser difícil com bico 0.4mm.",
      "fix": "Aumentar para 1.2mm para garantir impressão limpa."
    }
  ],
  "summary": "3 ajustes realizados: chanfro no furo USB elimina necessidade de suporte, tolerâncias corretas para montagem de conectores, e espessura mínima de slots corrigida.",
  "optimized_code": "// Arduino Uno Enclosure — Otimizado para FDM\n..."
}
```

> 💡 **Conceito-chave:** A LLM atua como **revisor técnico especializado** — ela "conhece" as restrições físicas do processo de impressão 3D e aplica correções justificadas.

---

## Etapa 5 — Configurações de Impressão

**Resultado:**
```json
{
  "material": "PETG",
  "nozzle_mm": 0.4,
  "layer_height_mm": 0.2,
  "first_layer_height_mm": 0.3,
  "infill_percent": 25,
  "infill_pattern": "gyroid",
  "wall_count": 4,
  "supports": "normal",
  "support_style": "tree",
  "bed_temp_c": 80,
  "nozzle_temp_c": 240,
  "print_speed_mms": 50,
  "cooling": "partial",
  "orientation_tip": "Imprimir com a base voltada para baixo; tampa em impressão separada.",
  "estimated_time_hours": 4.5,
  "estimated_filament_g": 68,
  "notes": [
    "PETG adere bem ao vidro com cola de bastão",
    "Primeira camada 20% mais lenta para melhor adesão",
    "Suportes em árvore para o furo USB — mais fácil de remover"
  ]
}
```

> 💡 **Conceito-chave:** O agente não só projeta a peça — ele "pensa" sobre como fabricá-la, ajustando parâmetros conforme o material e a geometria específica.

---

## Etapa 6 — BOM e Sourcing de Peças

**Resultado:**
```json
{
  "bom": [
    {"item": "PETG Filament 1kg Black", "qty": 1, "sku": "FIL-PETG-BK", "unit": "spool", "price_brl": 119.90, "in_stock": true},
    {"item": "M3×8mm Socket Head Cap Screw", "qty": 4, "sku": "HW-M3x8", "unit": "50 pcs", "price_brl": 12.90, "in_stock": true},
    {"item": "M3 Brass Heat-Set Insert (4×5mm)", "qty": 4, "sku": "HW-M3I", "unit": "50 pcs", "price_brl": 28.00, "in_stock": true, "notes": "Usar ferro de solda para instalar (200°C)"}
  ],
  "total_estimated_brl": 160.80,
  "print_material_sku": "FIL-PETG-BK",
  "sourcing_notes": "Todos os itens disponíveis no catálogo. Parafusos e inserts vendidos em packs — sobras reutilizáveis em outros projetos."
}
```

---

## Resumo do Pipeline

| Etapa | Ferramenta | Artefato gerado | Tipo de inteligência |
|-------|-----------|----------------|---------------------|
| 1 | `create_design_brief` | JSON estruturado | NLP → Schema |
| 2 | `generate_openscad_code` | Código CAD | LLM como engenheiro |
| 3 | `render_model` | PNG + STL | Compilador externo (ferramenta) |
| 4 | `optimize_design` | Código revisado + issues | LLM como revisor técnico |
| 5 | `suggest_print_settings` | Config de slicer | LLM como especialista em impressão |
| 6 | `source_parts` | BOM + preços | LLM + catálogo estruturado |

---

## Conceitos Ilustrados

| Conceito | Onde aparece |
|----------|-------------|
| **LLM como gerador de código** | Etapa 2: agente produz código OpenSCAD funcional |
| **Ferramenta externa via subprocesso** | Etapa 3: OpenSCAD CLI compilando o código gerado |
| **Artefato como contexto cumulativo** | Brief da Etapa 1 é insumo de todas as etapas seguintes |
| **LLM como revisor especializado** | Etapa 4: checklist de printabilidade FDM |
| **Degradação graciosa** | Etapa 3: pipeline continua mesmo sem OpenSCAD instalado |
| **Catálogo estruturado como ferramenta** | Etapa 6: lookup de SKUs vs. alucinação de peças |
| **Output estruturado em cada etapa** | Cada ferramenta retorna JSON tipado, não texto livre |

### Por que isso importa além do 3D

O mesmo padrão funciona em qualquer pipeline de "design → fabricação":

```
Descrição em texto
   ↓ Brief estruturado (LLM)
   ↓ Código / especificação (LLM)
   ↓ Compilação / validação (ferramenta especializada)
   ↓ Revisão técnica (LLM com regras de domínio)
   ↓ Parâmetros de processo (LLM especialista)
   ↓ Lista de materiais (LLM + catálogo)
```

Outros domínios: circuitos PCB (KiCad), infra como código (Terraform), pipelines de dados (dbt).
