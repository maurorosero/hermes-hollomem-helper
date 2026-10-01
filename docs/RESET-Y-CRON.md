# Memoria holográfica — reset y reconstrucción

**Fecha:** 2026-09-30 · **Ejecutado por:** Andrea · **Aprobado por:** Mauro

## Qué se hizo

### 1. Reset completo de los facts

```
ANTES:   facts=17  entities=16  fact_entities=16  banks=3  fts=17
DESPUÉS: facts=0   entities=0   fact_entities=0   banks=3  fts=0
```

Se borraron **solo** las filas de hechos y sus vínculos. Se conservaron `memory_banks`
(3) y el schema. `VACUUM` aplicado.

**Verificación funcional tras el reset:** `MemoryStore` abre, `add_fact` escribe,
`remove_fact` borra — la base quedó vacía y usable.

### 2. Salvaguarda (antes de borrar)

```
~/.hermes/backups/facts-reset-20260930-195659/
  memory_store.db               backup verificado (17 hechos, max_id=273)
  pre-reset.db                  copia inmediata pre-borrado
  hechos_actuales.json          los 17 con contenido, trust, fechas
  hechos_borrados_recuperados.json   265 textos históricos con su conteo de uso
  schema.sql                    16 objetos
  reset_resultado.json          antes/después
```

Backup hecho con la **API de backup de SQLite**, no con `cp` (WAL activo → copia
inconsistente; ya costó una colisión de ids en esta sesión).

**Reversión:** copiar `pre-reset.db` sobre `memory_store.db` con el gateway parado.

### 3. El hallazgo que motivó todo

De las 27.388 líneas de hecho inyectadas históricamente (medidas en
`messages.api_content`), solo el **23.7%** mapeaba a un hecho vivo:

```
recuperaciones de hechos VIVOS:     6.481
recuperaciones de hechos BORRADOS: 20.907   ← 3x más
```

**Los hechos más usados de la historia estaban borrados:**

```
1714x  "Usuario prefiere que Andrea se refiera a sí misma en primera persona femenina"
 962x  "SOUL.md actualizado con metodología de 5 pasos: investigar → analizar..."
 841x  "Andrea se compromete a dar lo mejor de sí cuando Mauro reconstruya a Hex"
 754x  "Mauro no quiere un 'yes-man'. Espera que Andrea le rebata cuando cree..."
 617x  "Lección: Siempre usar primera persona femenina (yo, mí, mi)..."
```

La tabla tenía **256 huecos** (`min=1, max=273, count=17`) y **no hay tabla de
auditoría**: no queda registro de qué se borró ni por qué.

**Ninguno de los 17 sobrevivientes figura entre los 15 más usados.** Se conservó lo
que nadie leía, y se perdió lo que más se usaba.

### 4. El cron de alimentación

```
job_id:   5d27f26f18b7
nombre:   Alimentar memoria holografica
schedule: every 3h    no_agent: true    deliver: origin
script:   ~/.hermes/scripts/hollomem-alimentar.py   (wrapper)
motor:    ~/developers/hermes/plugins/hermes-hollomem-helper/cron/alimentar.py
estado:   ~/.hermes/plugin-data/hermes-hollomem-helper/
```

**Costo en el agente principal: 0** (modo `no_agent`: subprocess sin LLM del arnés).

### 5. El circuito

```
1. lee state.db: bloques [CONTEXT COMPACTION] no completados
2. extrae candidatos de las secciones del resumen
3. JEV decide: hay_hecho / es_efimero / es_procedimiento     ~0.5 s c/u
4. reglas deterministas ANOTAN (no descartan)
5. redacta -> hecho <=275 chars
6. escribe con add_fact real + trust 0.35 + 0.30*P
7. watchdog: verifica que el prefetch siga inyectando hechos
```

### 6. Decisiones de diseño, con su medición

**El compresor de compactación es el insumo, no el turno crudo.** `hay_hecho`
0.78–0.87 vs 0.11–0.73 de los turnos sueltos, **sin solapamiento**. 98 tok por
candidato contra 311. Y consolida: el resumen ya fusionó los duplicados.

**Las reglas anotan, no filtran** (fuera de muestra, 616 candidatos):

```
falso negativo: 118 -> JEV los descarta igual. NO pierde hechos.
falso positivo:  75 -> 13 valían la pena. SE PIERDEN sin que JEV los vea.
el filtro costaba 13 hechos para ahorrar 134 s = 10 s por hecho perdido
```

Y mata preferentemente material irrecuperable: los datos jurídicos y tributarios
llevan números y fechas, que es exactamente lo que activa la regla.

**El umbral de contradicción es 0.7, no 0.5.** JEV separa contradicciones reales
en **0.88–0.97** y controles en **0.04–0.12**, sin solapamiento. Con 0.5 se
detenían pares **complementarios** (el `.env` no es secreto / los secretos viven
en Infisical: ambas ciertas).

**La contradicción no se resuelve sola.** Cuando JEV detecta que un hallazgo nuevo
contradice uno existente, **no se escribe y no se reescribe el viejo**: se reporta.
La memoria no cambia una creencia sobre el mundo por sí misma.

## Defectos encontrados y corregidos durante la construcción

Cada uno se detectó corriendo de verdad, y varios habrían sido silenciosos:

1. **La pregunta `hay_hecho` rechazaba el 100% de las reglas de trabajo.**
   Decía *"NO es una instrucción"*, y los candidatos más valiosos del resumen
   **son citas de instrucciones y correcciones de Mauro**. Medido: **0/6 → 6/6**
   al reformularla. Este era el defecto más grave: habría dejado la memoria sin
   las reglas de conducta.

2. **La deduplicación era inalcanzable por diseño.** El umbral estaba sobre
   `score` de `search()`, y `score = relevancia × trust × decay`: el trust acota
   el score (~0.5 en hechos nuevos), así que **un umbral de 0.75 no se alcanza
   nunca**. La primera corrida real generó **19 pares casi-duplicados**.

   La causa de los duplicados, medida: **los resúmenes de compactación son
   acumulativos** — el mismo hallazgo reaparece en bloques sucesivos (10% del
   contenido está en más de un bloque). El mismo texto procesado dos veces da
   **dos redacciones distintas** del mismo hecho.

   Corregido con **dos señales**: similitud de texto (≥0.55) **o** JEV
   *"¿afirman lo mismo?"* (≥0.5). La segunda es necesaria porque dos redacciones
   que reordenan las palabras dan similitud ~0.50, por debajo de cualquier umbral
   útil. Medido contra pares reales: JEV acierta los que el texto pierde
   (0.78–0.94) y **no marca los que son distintos** (0.02–0.27).

3. **El redactor agregaba justificaciones.** Los hechos salían terminando en
   *"ya fallé"*, *"ya causó errores"*. El hecho debe **afirmar** la regla, no
   narrar el incidente. Corregido con reglas explícitas y ejemplo.

4. **`pendientes` marcaba como vistas huellas sin evaluar.** Si el tope de juicios
   cortaba, esos candidatos **nunca se re-evaluaban**: se perdían. Ahora solo se
   marcan las huellas que pasaron realmente por JEV. Verificado: **60 candidatos
   sin evaluar quedaron sin marcar**.

5. **Cursor monotónico.** El primer diseño avanzaba `ultimo_msg_id`, y con topes
   salteaba bloques sin procesar. Reemplazado por una **lista de bloques
   completados**.

6. **`search` no está en `MemoryStore`.** Vive en `FactRetriever`. Cargaba solo el
   store y moría con `AttributeError`.

7. **`add_fact` devuelve un `int`,** no un dict.

8. **Escritura silenciosa del cron.** Como `no_agent`, el stdout se entrega
   verbatim: el detalle de cada hecho habría llegado a Telegram. Ahora el detalle
   va al log y solo sale un resumen de una línea — y **nada** si no hubo nada
   (patrón watchdog).

## Estado final

```
34 hechos (tras la fusión)  ->  32 (tras unificar 2 pares residuales mas)
todos con hrr_vector y en FTS
trust 0.51 - 0.71
max similitud entre pares: 0.535 (ninguno es duplicado)
```

**Backups de la operación completa:**

```
facts-reset-20260930-195659/        pre-reset.db + los 265 hechos recuperados
facts-fusion-20260930-202201/       fusion por texto (62 -> 39)
facts-fusion-jev-20260930-202256/   fusion por JEV (39 -> 36)
```

Cada uno con su JSON de detalle (qué se conservó, qué se borró, por qué).


## Lo que NO está verificado

- **La detección de contradicciones son 8 pares construidos**, no una muestra.
  El umbral 0.7 se apoya en esa separación; con más casos podría moverse.
- **`half_life` sigue en 0.** El decay está implementado y probado (nunca descarta,
  solo baja el score), pero apagado.
- **El backlog es grande**: 5.000+ candidatos históricos. El cron drena 120 por
  corrida cada 3 h.
- **No se sabe por qué se borraron los 256 hechos.** Sin tabla de auditoría, no
  hay forma de reconstruir la causa.

## `retrieval_count`: cerrado como NO VIABLE (decisión, no deuda)

Se investigó alimentarlo desde el historial y **se descartó con evidencia**. Queda
registrado para que no se reintente sin motivo.

**El dato SÍ era derivable.** El `prefetch` escribe cada turno un bloque
`## Holographic Memory` con hasta 5 líneas `- [trust] contenido`, y el contenido va
**literal** (sin transformar); ese bloque queda en `state.db` → `messages.api_content`.
Contar líneas y mapear por texto exacto da las recuperaciones reales: **27.413 líneas
en 5.932 bloques**, sin tocar el core ni heredar `prefetch`.

**Por qué se descartó — la fórmula lo ignora.** Verificado en el árbol completo de
Hermes: `retrieval_count` aparece **3 veces**, todas inertes — dos SELECT que lo traen
al dict y el DDL que lo declara. **Cero usos en cálculos.** El ranking real
(`retrieval.py:69`) es:

```python
fact["score"] = relevance * fact["trust_score"]
```

No hay aritmética sobre el campo, ni `ORDER BY` que lo use, ni un test que lo toque.
El historial de git lo confirma: ningún commit lo incrementó jamás (`git log -S`
devuelve solo un refactor de despacho y un merge). **No es una regresión: es una
función declarada en el esquema y nunca implementada** — el propio
`paper-memoria-es.md` §5.4 ya lo documentaba.

**Reversión aplicada.** Se escribieron 13 conteos (10 hechos) y se revirtieron a 0.
Un contador que afirma un uso que nadie consume es un dato **falso**, no incompleto:
0 es el estado honesto. Ningún hecho se tocó.

**Regla que queda:** no se alimenta un campo que ningún consumidor lee. Si algún día
se quiere pesar el uso, **primero** el scoring tiene que usarlo — y eso exige
reemplazar el provider `holographic` bundled (`HERMES_ENABLE_PROJECT_PLUGINS` +
drop-in systemd, no `HERMES_BUNDLED_PLUGINS`, que reemplaza en vez de sumar y tumbó
Telegram 9 h 25 min). **Sin consumidor, el cron no se construye.**

**Corrección (medida después): el lote NO era material a rescatar.** La afirmación
inicial —*"el valor real es el uso histórico para decidir qué reingresar"*— quedó
**refutada por los datos**:

```
slots del prefetch (5 por turno, 5.936 bloques = 27.433 slots)
  gastados en hechos VIVOS    :     33   ( 0.1%)
  gastados en hechos BORRADOS : 27.400   (99.9%)
     de esos, repetian algo que el SOUL.md YA dice: 6.102  (22.2%)
  bloques con >=1 linea redundante con el SOUL: 3.695 / 5.936  (62%)
```

**De cada 5 slots de recuperación, 1,03 se iba en repetir lo que el SOUL.md ya
garantiza cada turno, y prácticamente el resto citaba hechos ya inexistentes.** El
mecanismo estaba roto: el prefetch elegía casi exclusivamente material muerto y
desplazaba a los hechos vivos. Eso es *"rompían lo que hacemos ahora"*, y explica
por qué los 33 hechos de hoy reciben 33 recuperaciones contra 27.400 inútiles.

**Los 265 no se reingresan.** Y no hace falta que se reingresen: el cron construido
**re-deriva** los hechos desde los resúmenes de compactación, que es la fuente viva.
Lo que siga siendo cierto vuelve solo, ya redactado y sin el lastre. Rescatarlos en
bloque habría restaurado justamente el ruido que rompía la inyección.

**Lo único que merecía revisión individual** eran los 4 hechos de mayor uso de la
lista, aprobados uno por uno por Mauro. **Se recargaron con el procedimiento actual**
(no se restauró el texto viejo), el 2026-09-30:

```
#339  trust 0.58  libreta propia de Andrea (contacts) aloja agentes; la de Mauro, humanos
#340  trust 0.54  infraestructura local de Andrea, dirección en la casa de Mauro
#341  trust 0.61  relaciones de vCards de la libreta de Mauro son implícitas con Mauro
#342  trust 0.54  el plan de máquina con GPU sigue siendo plan, no estado
```

Método (`recargar_rescatados.py`): se le pasa al redactor del motor el **contexto
verificado hoy**, no el texto viejo — así no arrastra la redacción anterior ni datos
caducados. Luego el camino normal: JEV → redacción ≤275 chars → duplicado (texto +
JEV) → contradicción (umbral 0.7) → `add_fact` + `update_fact(trust_delta)`. El trust
sale de la curva `0.35+0.30×P`, **no del trust viejo** (que era 0.90–1.00 inflado).

Qué se verificó antes de redactar, contra la fuente y no contra la memoria:

- **Los agentes en `contacts`**: la libreta tiene 2 contactos — Mauro (`RELATIONSHIP:
  FATHER`) y Andrea (`RELATIONSHIP: CHILD`, categoría `agents`). Confirmado en el
  servidor.
- **La dirección**: se tomó **literal del vCard de Mauro**, no de la memoria.
- **`contacts_shared_by_mrosero`**: 386 contactos, todos humanos
  (`family`/`friend`/`prospect`/`backlog`). Ningún agente.
- **El plan de GPU**: verificado que **no se ejecutó** — sin GPU dedicada (solo Intel
  HD Graphics 530 integrada, sin NVIDIA), host local (`systemd-detect-virt = none`).

Efecto colateral medido: al pasar por `add_fact`, **las entidades subieron de 2 a 9**.

