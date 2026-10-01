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

2. **El redactor agregaba justificaciones.** Los hechos salían terminando en
   *"ya fallé"*, *"ya causó errores"*. El hecho debe **afirmar** la regla, no
   narrar el incidente. Corregido con reglas explícitas y ejemplo.

3. **`pendientes` marcaba como vistas huellas sin evaluar.** Si el tope de juicios
   cortaba, esos candidatos **nunca se re-evaluaban**: se perdían. Ahora solo se
   marcan las huellas que pasaron realmente por JEV.

4. **Cursor monotónico.** El primer diseño avanzaba `ultimo_msg_id`, y con topes
   salteaba bloques sin procesar. Reemplazado por una **lista de bloques
   completados**.

5. **`search` no está en `MemoryStore`.** Vive en `FactRetriever`. Cargaba solo el
   store y moría con `AttributeError`.

6. **`add_fact` devuelve un `int`,** no un dict (ya me había pasado antes).

7. **Escritura silenciosa del cron.** Como `no_agent`, el stdout se entrega
   verbatim: el detalle de cada hecho habría llegado a Telegram. Ahora el detalle
   va al log y solo sale un resumen de una línea — y **nada** si no hubo nada
   (patrón watchdog).

## Lo que NO está verificado

- **La detección de contradicciones son 8 pares construidos**, no una muestra.
  El umbral 0.7 se apoya en esa separación; con más casos podría moverse.
- **`retrieval_count` sigue sin alimentarse.** La capa de uso no se captura, así
  que el ranking no puede subir por uso ni bajar por desuso. **Es la pieza que
  falta, y es la que habría evitado que se borraran los hechos más usados.**
- **`half_life` sigue en 0.** El decay está implementado y probado (nunca descarta,
  solo baja el score), pero apagado.
- **El backlog es grande**: 5.000+ candidatos históricos. El cron drena 120 por
  corrida cada 3 h.
- **No se sabe por qué se borraron los 256 hechos.** Sin tabla de auditoría, no
  hay forma de reconstruir la causa. El `retrieval_count` en 0 significa que
  **nadie podía saber cuál era el más usado al momento de borrarlo**.
