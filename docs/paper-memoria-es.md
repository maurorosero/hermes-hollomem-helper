---
title: "El reparto de la memoria en arneses de agentes: por qué un archivo de contexto no puede ser la única memoria y por qué el olvido se delega al almacén externo"
short_title: "El reparto de la memoria en arneses de agentes"
author: "Mauro Rosero"
affiliation: "ROSERO ONE"
email: "maurorosero@gmail.com"
date: "2026-09-28"
version: "0.1-draft"
type: "case-study"
status: "borrador para revisión del autor"
venue_target: "Inteligencia Artificial (IBERAMIA) — Open Access, doble ciego"
license: "CC BY-NC 4.0"
language: "es"
abstract_language: "en"
keywords_es: "arnés de agente, jerarquía de memoria, economía de tokens, olvido selectivo, memoria holográfica, criterio de asignación, estudio de caso"
keywords_en: "agent harness, memory hierarchy, token economics, selective forgetting, holographic memory, assignment criterion, case study"
---

# El reparto de la memoria en arneses de agentes: por qué un archivo de contexto no puede ser la única memoria y por qué el olvido se delega al almacén externo

## Resumen

Los arneses de agentes de producción separan la memoria en dos capas: un archivo inyectado en cada turno (en adelante **core**, del arnés Hermes: `MEMORY.md` y `USER.md`) y un almacén externo de hechos recuperados por consulta (**archival**, en este caso un store holográfico). Este trabajo documenta un estudio de caso sobre el **criterio de reparto** entre ambas capas, y sostiene una tesis operativa: el problema no está en que existan dos capas, sino en **dejar a la deriva qué entra en cada una**. Medido sobre un sistema en producción real (1.759 sesiones, 66.559 mensajes, 256 hechos), encontramos tres fallos que se componen: (a) el 54 % de los hechos del almacén externo superan los 600 caracteres y funcionan como documentos, no como hechos; (b) el mecanismo de recuperación por consulta producía ~11 KB por corrida de los cuales **se descartaba el 91 %**, por un tope de previsualización que el propio agente no percibía; y (c) el mecanismo de peso del almacén (`trust_score`, decaimiento temporal) existía en el código pero estaba **plano o apagado**, de modo que la capa que debía auto-depurarse no se depuraba. La literatura de 2026 es consistente con el diagnóstico: un store sin compuerta de escritura cae de 97,8 % a 13,3 % de precisión con 80 % de distractores (Zahn & Chana, 2603.15994); la construcción domina el ciclo de vida y todos los sistemas evaluados acumulan estado de forma monotónica por defecto (2606.06448); y la elección entre memoria por hechos y contexto largo es una **decisión de costo, no de capacidad** (Pollertlam et al., 2603.04814) — resultado que este trabajo no contradice sino que usa para fundar el reparto: el contenido extenso merece **su propia fuente consultable** (el wiki curado y el corpus de investigación), no un prefijo permanente. El aporte de este trabajo es el criterio de reparto explícito —tres preguntas de decisión—, la formalización de los **cuatro destinos** de la memoria (§3.1) y la medición honesta de un sistema donde el mecanismo formal era correcto y el uso lo había desbordado.

**Palabras clave:** arnés de agente, jerarquía de memoria, economía de tokens, olvido selectivo, criterio de asignación.

## Abstract

Production agent harnesses split memory across two layers: a file injected on every turn (the **core**: `MEMORY.md`, `USER.md`) and an external store retrieved on demand (the **archival** layer, here a holographic fact store). This paper documents a case study of the **assignment criterion** between both layers, arguing that the defect is not the existence of two layers but **leaving what goes into each one ungoverned**. Measured on a live system (1,759 sessions, 66,559 messages, 256 facts), three compounding failures appear: (a) 54 % of stored facts exceed 600 characters and behave as documents rather than facts; (b) the query-time retrieval path produced ~11 KB per run of which **91 % was discarded**, due to a preview cap the agent itself never noticed; and (c) the store's own weighting machinery (`trust_score`, temporal decay) existed in code but was **flat or disabled**, so the layer meant to self-prune did not prune. The 2026 literature agrees: an ungated store drops from 97.8 % to 13.3 % accuracy with 80 % distractors (Zahn & Chana, 2603.15994); construction dominates the lifecycle and every evaluated system accumulates state monotonically by default (2606.06448); and fact-based memory vs. long context is a **cost decision, not a capability decision** (Pollertlam et al., 2603.04814) — a finding this work does not contradict but uses to ground the split: extensive content deserves **its own queryable source** (the curated wiki and the research corpus), not a permanent prefix. The contribution is the explicit assignment criterion — three decision questions — the formalization of the **four destinations** of memory (§3.1), and an honest measurement of a system where the formal mechanism was sound and its usage had overrun it.

**Keywords:** agent harness, memory hierarchy, token economics, selective forgetting, assignment criterion, case study.

## 1. Introducción

### 1.1 El problema

Un agente con memoria persistente tiene, como mínimo, dos lugares donde guardar cosas: uno que se lee en cada turno y otro que se consulta cuando hace falta. El primero se paga siempre. El segundo, casi nunca.

La creencia razonable es que basta con hacer bien el mecanismo: si el almacén externo tiene decaimiento y pesos, se depurará solo; si el archivo de contexto tiene un tope duro, no crecerá. En la práctica observamos lo contrario. El almacén externo que debía depurarse tenía su maquinaria **apagada**; el archivo de contexto, que no se depura, estaba **al 98 %** de su capacidad.

El problema que este trabajo aborda no es de mecanismo. Es de **gobierno**: sin un criterio explícito de qué entra en cada capa, el sistema se satura en ambas direcciones a la vez — el archivo se llena de datos de dominio que caducan, y el almacén se llena de documentos que no se pueden recuperar.

### 1.2 La pregunta

¿Qué criterio decide qué va en la memoria inyectada en cada turno y qué va al almacén externo, cuando ambas coexisten?

### 1.3 La propuesta en una frase

**Que el criterio se decida por uso y por caducidad, no por contenido**: a la capa que se paga siempre va lo que no tiene tema propio y no caduca; al almacén externo va lo específico, que sí puede cambiar, porque **es la única de las dos capas que se puede depurar sin intervención humana**.

### 1.4 Aporte y alcance

Este trabajo aporta:

1. **Un criterio de reparto explícito y ejecutable** (§4.2), expresado como tres preguntas de decisión ordenadas, con el contraejemplo de cada una.
2. **La medición de un sistema real** (§5) donde los tres fallos —tamaño de los hechos, tope silencioso en la entrega, pesos apagados— se componen, con los números crudos y el método para reproducirlos.
3. **La contrastación con la literatura de 2026** (§2), que converge con el diagnóstico empírico del autor, y los puntos donde la evidencia contradice la intuición del caso.

**Alcance y límites declarados desde el inicio.** Es un estudio de caso único (*n* = 1 sistema), no un experimento controlado. Las cifras son mediciones del sistema estudiado, no estimaciones de efecto. Las afirmaciones conductuales —si el criterio mejora la conducta del agente— quedan **NO DETERMINABLES** con los datos disponibles, y se declaran como tales en §6.5. Este trabajo **no** sostiene que la memoria por hechos sea superior al contexto largo, y no necesita hacerlo: la comparación publicada favorece al contexto largo en precisión (§2.4), y ese resultado es coherente con el diseño medido — el contenido extenso vive en fuentes de **contexto largo dedicadas** (el wiki curado y el corpus de investigación), invocadas por consulta. La tesis que se sostiene es más simple y más fuerte: **ninguna fuente debe invocarse siempre y para todo**, y la única capa que se paga en cada turno debe ser mínima.

### 1.5 Organización

§2 sitúa el trabajo frente a la literatura. §3 describe el arnés y sus dos capas. §4 presenta el método y el criterio de reparto. §5 reporta las mediciones. §6 discute, incluido lo que no se puede sostener. §7 enumera las amenazas a la validez. §8 propone el trabajo futuro y §9 concluye.

## 2. Trabajo relacionado

### 2.1 La arquitectura de tres capas es una convergencia, no una elección

La separación entre memoria residente en contexto y almacén externo no es una peculiaridad del arnés estudiado. MemGPT (Packer et al., 2024) la formuló explícitamente como una jerarquía inspirada en sistemas operativos: *paging* entre contexto principal, base de recuerdos y almacén de archivo vectorial. El relevamiento de Du (2603.07670) organiza el campo en cinco familias de mecanismos —compresión residente en contexto, almacenes aumentados por recuperación, auto-mejora reflexiva, contexto virtual jerárquico y gestión aprendida por política— y señala que la jerarquía virtual es la familia donde se ubica esta arquitectura.

La consecuencia relevante para este trabajo: **la existencia de dos capas está establecida; el criterio de qué va en cada una, no.** El relevamiento cierra con un conjunto de desafíos abiertos que incluye *learned forgetting* —olvido aprendido— y *continual consolidation* —consolidación continua—, exactamente las dos funciones que en el sistema estudiado estaban declaradas y no ejercidas.

### 2.2 Qué pasa cuando la escritura no tiene compuerta

La literatura mide el costo de guardar sin filtrar, y lo mide con márgenes grandes.

| Medición | Fuente | Cifra |
|---|---|---|
| Store sin compuerta, 80 % de distractores | Zahn & Chana, **2603.15994** (16-mar-2026) | Precisión **13,3 % ± 4,7 %** sin compuerta → **97,8 % ± 1,1 %** con compuerta completa |
| Señal de novedad aislada vs. compuesta | ídem | Novedad sola **58,0 % ± 19,4 %**; reputación + novedad **96,4 % ± 1,4 %** (a **−1,4 pp** del juego completo, 97,8 %) |
| Acumulación por defecto | **2606.06448** (4-jun-2026) | *«Todos los sistemas evaluados acumulan estado monotónicamente por defecto; los operadores deben añadir políticas independientes de poda o olvido»* |
| Sesgo de la medición ingenua | **2607.11149** (13-jul-2026) | *«La medición ingenua a nivel de bytes subestima la duplicación por un orden de magnitud»*; mitigación content-addressed: retención **4,8×–32,7× menor** |
| Memoria sin presupuesto | **2606.13177** (11-jun-2026) | El store *«se llena de entradas redundantes que inflan el costo y **degradan el retrieval desplazando a la evidencia más útil**»* |
| Degradación operativa en 72 h | MemTier, **2605.03675** (5-may-2026) | El éxito de ejecución de herramientas **se degrada 14 puntos porcentuales en ventanas de 72 horas** |

El hallazgo de Zahn & Chana importa por su forma, no solo por su magnitud: **el store no se degrada suavemente, se derrumba**, y los distractores —el 80 % del contenido almacenado— son a los que el modelo «atiende preferentemente». Es la formalización de lo que en el sistema estudiado se observó de otra manera: hechos convertidos en documentos que desplazan a la evidencia útil.

### 2.3 El olvido es una función, no un defecto

La literatura no trata el olvido como una concesión. Fofadiya y Tiwari (**2604.02280**, 2-abr-2026) reportan que la retención persistente sin control produce *«decaimiento temporal y propagación de memorias falsas»*, con degradación de **0,455 a 0,05** en las etapas de LOCOMO/LOCCO, y **78,2 % de precisión con 6,8 % de tasa de memoria falsa** en MultiWOZ bajo retención persistente. Su marco de olvido con presupuesto acotado integra recencia, frecuencia y alineación semántica, y mejora F1 de largo horizonte **más allá del nivel base de 0,583** sin aumentar el uso de contexto.

Rana et al. (**2604.00131**, 31-mar-2026) proponen `Oblivion`, un control auto-adaptativo con **activación guiada por decaimiento** y recuperación con compuerta de incertidumbre. Y MemoryBank (Zhong et al., **2305.10250**, AAAI 2024) implementa un mecanismo de actualización inspirado en la **curva de olvido de Ebbinghaus**: el sistema olvida y refuerza según el tiempo transcurrido y la significancia relativa del recuerdo.

Esa es exactamente la forma del mecanismo del sistema estudiado: decaimiento exponencial `0,5^(días/media_vida)`. La diferencia —y es el hallazgo central de §5— es que **el parámetro estaba en cero**, es decir, el reloj estaba parado.

### 2.4 Memoria por hechos contra contexto largo: una decisión de costo

Este es el punto donde la evidencia externa **corrige** la intuición del caso, y conviene declararlo de frente.

Pollertlam et al. (**2603.04814**, 5-mar-2026) comparan pasar el historial completo a un modelo de contexto largo contra mantener un sistema de memoria que extrae y recupera hechos. Hallan que **en precisión gana el contexto largo**, por un margen de aproximadamente **33 a 35 puntos porcentuales** en dos de tres pruebas. El argumento de la memoria por hechos **no es de precisión**: es que el pipeline condensa conversaciones de ~101.600 tokens en hechos atómicos de **~2.909 tokens por usuario**, y que el sistema de memoria **adelanta el costo en la escritura** mientras el contexto largo lo paga en cada turno. La elección se vuelve favorable a la memoria a partir de un punto de equilibrio medible en turnos (`N_BE`, el turno en que el costo de la memoria cae por debajo del de contexto largo), cuya posición depende de la longitud de contexto y del volumen de datos.

El trabajo de Dadhich (**2607.21503**, 23-jul-2026) refuerza el marco: plantea el problema como **de ciclo de vida y de arquitectura**, y señala que el contexto de adición completa crece **cuadráticamente** con la longitud de la conversación, mientras la summarización cruda da costo lineal a expensas de precisión.

**Consecuencia para la tesis de este trabajo: este resultado no la contradice, la confirma.**

El autor no sostiene que la memoria por hechos sea más precisa que el contexto largo. Sostiene algo distinto y compatible con la evidencia: que **el contenido extenso no debe invocarse siempre y para todo, sino solo cuando se requiere**. En el sistema estudiado eso se materializa en una arquitectura de cuatro destinos, no dos (§3.1): el contenido largo y curado vive en fuentes dedicadas —el **wiki** consolidado y el **corpus de investigación**—, cada una invocada por consulta; el almacén de hechos cubre lo específico y caducable; y solo el residuo sin tema propio ni caducidad ocupa la capa que se paga en cada turno.

Visto así, la ventaja de precisión del contexto largo (33-35 pp en dos de tres pruebas) **no es un argumento contra la memoria por hechos: es la razón por la que el contexto largo merece su propia fuente**. Si el historial completo es más preciso, la conclusión correcta no es «inyectemos el historial», sino «**tengámoslo disponible y traigámoslo cuando el tema lo requiera**». Eso es lo que el wiki curado hace mejor que el historial crudo: está consolidado, es navegable por índice y no se paga por turno.

Los dos argumentos que sostienen la tesis del autor son entonces:

1. **Costo:** lo que se inyecta siempre crece de forma insostenible (§2.4), y el presupuesto de atención es finito y medido en reglas, no solo en tokens (§2.5).
2. **Olvido:** solo una capa externa permite política de olvido, que la evidencia señala como condición de estabilidad a largo horizonte (§2.3).

La precisión no es un eje de la tesis, y este trabajo no la invoca como tal.

### 2.5 Por qué el reparto importa: el costo de lo que se paga siempre

El contenido de la capa residente se paga en **cada llamada al modelo**, y además queda sujeto a una restricción medida del lado de la instrucción: la degradación por volumen de restricciones simultáneas. Los trabajos relevados en la base local del proyecto (§5.6) reportan que el cumplimiento conjunto decae de forma marcada pasadas **5-6 restricciones** y que la acumulación de fallos es **multiplicativa**, no aditiva (Vasileva, **2608.12426**). Esto tiene una consecuencia directa sobre el reparto: cada entrada que se agrega al core no solo cuesta tokens, **compite con las demás reglas del mismo presupuesto de atención**.

Es el argumento de economía que el autor sostiene empíricamente, y la literatura lo respalda por dos vías independientes: costo por turno (§2.4) y densidad de restricciones (§2.5).

### 2.6 El hueco que este trabajo ocupa

La literatura mide con rigor **qué guardar** (§2.2), **cómo olvidar** (§2.3) y **cuánto cuesta la elección de arquitectura** (§2.4). Lo que no encontramos documentado con la misma especificidad es **el criterio de reparto entre capas cuando ambas coexisten en el mismo arnés**: la pregunta «este dato, ¿va al archivo que se paga siempre o al almacén que se consulta?». Los arneses de producción revisados publican qué va en su archivo de memoria, pero no publican el criterio discriminatorio, y ninguno publica evidencia de que su límite numérico tenga respaldo medido.

Este trabajo no llena ese hueco con un experimento, sino con un criterio explícito, su fundamento en la evidencia disponible, y la medición del costo de no haberlo tenido.

## 3. Contexto del arnés

### 3.1 El arnés y sus cuatro destinos

El sistema estudiado es un agente personal en producción sobre el arnés Hermes. La pregunta «¿dónde va este dato?» tiene **cuatro** respuestas posibles, no dos, y la distinción es el núcleo del reparto:

| Destino | Artefacto | Acceso | Costo | Depuración |
|---|---|---|---|---|
| **Core** | `MEMORY.md` (2.200 car.) y `USER.md` (1.375) | Inyectado en **cada turno**, congelado al inicio de sesión | Se paga siempre (~1.300 tokens por sesión) | **Ninguna automática**: consolidación a mano |
| **Archival** | `memory_store.db`, tabla `facts` | Recuperado **por consulta** | Se paga al recuperar | Pesos de confianza + decaimiento temporal |
| **Wiki curado** | `~/wiki` — metacapa, *content types* y evidencia cruda | Por **índice y consulta**: se lee `index.md` y se navega a la página | Se paga al consultar | Reingesta y recompilación por proceso |
| **Corpus de investigación** | `~/Research` — informes por ciclo y por tema | Por **tema y consulta** | Se paga al consultar | Versionado por ciclo; el ciclo siguiente revisa el anterior |

Los cuatro destinos se ordenan por **una sola variable: con qué frecuencia hace falta el contenido**.

```
se paga en cada turno    CORE            ← sin tema propio, sin caducidad
                         │
se invoca por tema       ARCHIVAL        ← específico, caducable
                         │
se invoca por consulta   WIKI CURADO     ← extenso, consolidado, navegable
                         │
se invoca por tema       RESEARCH        ← extenso, por ciclo de investigación
```

**Por qué el wiki y el corpus son destinos propios y no «contexto largo» genérico.** El resultado de 2603.04814 (§2.4) —el contexto largo es más preciso que la memoria por hechos— **no implica inyectar el historial**. Implica que existe un lugar para el contenido extenso, y que su forma importa: el wiki está **consolidado** (páginas compiladas por proceso, con índice como punto de entrada y trazabilidad a la evidencia cruda en `raw/`), mientras el corpus de investigación está **versionado por ciclo**, con cada ciclo revisando el anterior. Ambos son navegables sin recorrerlos enteros, y ninguno se paga por turno. Esa es la forma correcta de tener «contexto largo» disponible: **como fuente consultable, no como prefijo permanente**.

**La consecuencia que el reparto busca:** la única capa que se paga siempre debe quedar reducida al residuo que **no tiene tema propio y no caduca**. Todo lo demás tiene un destino donde se invoca cuando se requiere.

Ambas capas escriben como **afirmaciones sobre el mundo**, nunca como órdenes. La razón no es estilística: una entrada imperativa en el core se relee en cada sesión como una directiva vigente y puede **sobrescribir la intención actual del operador**. Se trata de una regla de seguridad, no de estilo.

### 3.2 El mecanismo de recuperación y su tope

La capa de archivo expone una función `prefetch(query)` que el arnés invoca con la consulta del turno, y que recupera hasta **5 hechos** con confianza mínima 0,3, inyectándolos en el prompt de sistema bajo un encabezado propio.

Sobre esa salida actúa un mecanismo independiente: si el texto supera los **10.000 caracteres**, el arnés **no lo inyecta**. Lo escribe en disco —bajo `<HERMES_HOME>/hook_outputs/<sesión>/`— y coloca en su lugar una previsualización de **500 caracteres de encabezado más 500 de cola**. El agente ve un bloque de memoria con contenido plausible y **no recibe señal alguna de que el resto fue descartado**.

Este detalle es central para §5, y su relevancia va más allá del caso: es un modo de fallo **silencioso por diseño**, donde el mecanismo funciona como está especificado y el resultado es que la memoria recuperada no llega.

### 3.3 El mecanismo de peso

El ranking del almacén combina tres componentes y dos multiplicadores:

```
score = (fts·0,4 + jaccard·0,3 + hrr·0,3) · trust_score · decaimiento
        decaimiento = 0,5^(días / media_vida)
```

- **fts, jaccard, hrr**: similitud léxica y vectorial (representaciones holográficas reducidas).
- **trust_score**: confianza por hecho, con realimentación (+0,05 al marcarse útil, −0,10 al marcarse no útil).
- **decaimiento**: exponencial por antigüedad, con `media_vida = 0` **apagado por defecto**.

### 3.4 Qué debía pasar y qué pasó

El diseño es correcto y coincide con la literatura: una capa externa con pesos y decaimiento **es** una política de olvido. Lo que este trabajo documenta es la brecha entre el diseño y su operación.

## 4. Método

### 4.1 Tipo de estudio

Estudio de caso instrumentado sobre un sistema en producción, con medición directa del estado de ambas capas. No hay grupo de control ni asignación aleatoria; las cifras son **descripciones del sistema estudiado**, no estimaciones de efecto. Se reportan crudas, con el comando de verificación, para que puedan reproducirse y refutarse.

### 4.2 El criterio de reparto

El criterio es el aporte operativo de este trabajo. Se evalúa **en orden**, y la primera respuesta negativa cierra la decisión:

**Pregunta 1 — ¿Si este dato no estuviera en contexto, y su tema no apareciera en la conversación, yo haría algo mal?**
Si la respuesta es **no**, el dato no va al core. Es la pregunta discriminante. Un dato de dominio tiene tema propio: cuando el tema aparece, la consulta lo trae. Una regla de conducta **no tiene tema** — no existe una consulta que pregunte «cómo obedecer»—, y por lo tanto solo funciona si está delante.

**Pregunta 2 — ¿Puede cambiar con el tiempo?**
Si **sí**, va al almacén externo. La razón es estructural (§3.1): el core no tiene depuración automática, el almacén sí. Un dato caducable en el core es deuda técnica que alguien tendrá que pagar a mano.

**Pregunta 3 — ¿Está ya textualmente en el prompt de identidad?**
Si **sí**, no se duplica. El prompt de identidad se inyecta en cada turno igual que el core: escribirlo en ambos es pagarlo dos veces por lo mismo.

**La formulación de una línea que el autor usa como regla:** al core va lo que **no caduca y no tiene tema**; al almacén va lo específico, que **sí puede cambiar**.

**Nota sobre el fundamento.** La pregunta 2 no se justifica porque el almacén sea «más específico» —eso sería un criterio por contenido, que este trabajo rechaza—, sino porque **es la única capa con política de olvido**. La distinción es operativa: si mañana el core tuviera depuración automática, la pregunta 2 dejaría de ser discriminante.

### 4.3 Procedimiento de medición

Se midieron, sobre las dos capas y el historial:

1. **Composición del core**: número de entradas, tamaño, uso del presupuesto.
2. **Composición del almacén**: número de hechos, distribución de tamaños, valores de confianza, estado del decaimiento.
3. **Comportamiento del retrieval**: qué recupera `prefetch`, cuánto de lo recuperado llega al contexto, por lectura de los archivos de volcado.
4. **Cobertura del criterio**: cotejo de cada entrada del core contra el almacén, para saber si al retirarla quedaría recuperable.
5. **Frecuencia de uso**: recuento de mensajes y sesiones por tema sobre el historial completo.
6. **Correcciones del operador**: recuento y clasificación de los mensajes correctivos, para identificar el patrón de fallo recurrente.

### 4.4 Lo que este diseño no permite afirmar

No permite afirmar que el criterio **mejore la conducta**: para eso haría falta un banco de casos con verdad de referencia, que no existe. No permite afirmar causalidad entre el desorden medido y ningún síntoma conductual concreto. Y no permite generalizar a otros arneses: los números son de este sistema.

## 5. Resultados

### 5.1 El core estaba al 98 % y la mitad de su contenido no le correspondía

`MEMORY.md` contenía **13 entradas en 2.172 de 2.200 caracteres (98 %)**. Del análisis por categoría, **9 de las 13 eran datos de dominio** —un dispositivo, un agente, una propiedad, un proyecto, un cliente—, es decir, materia con tema propio y con capacidad de caducar.

El cotejo contra el almacén mostró algo más grave que la pertenencia mal asignada: **5 de las 13 entradas solapaban ≥50 % con un hecho que ya existía** en el almacén, y dos eran casi duplicados literales (88 % y 77 % de solape). No eran datos «que podrían ir» al almacén: **ya estaban ahí**.

### 5.2 La cobertura del criterio: 6 de 9 recuperables

Antes de proponer retirar las 9 entradas de dominio, se verificó si el almacén las devolvería cuando su tema apareciera, simulando el ranking de `prefetch` con la consulta típica de cada tema:

| Entrada | ¿Recuperable por consulta? |
|---|---|
| Agente y su infraestructura | **Sí** |
| Propiedad: dimensiones | **Sí** |
| Correlo de correo del agente | **Sí** |
| Playbooks de infraestructura | **Sí** |
| Base de investigaciones | **Sí** |
| Proyecto pendiente | **Sí** |
| Dispositivo móvil y su sensor | **No** |
| Métrica de contenido | **No** |
| Cliente: tasas y licencias | **No** |

**Resultado: 6 de 9.** De ahí sale una regla de procedimiento que el criterio por sí solo no da: **no se retira una entrada del core sin haber escrito antes el hecho que la hará recuperable**. El orden es escribir → verificar → retirar. Al revés se pierde el dato.

### 5.3 La entrega del retrieval descartaba el 91 %

Esta es la medición más importante del trabajo, porque revela un fallo que **el agente no podía percibir**.

Dos corridas de `prefetch` recuperaron **11.565 y 10.065 caracteres** respectivamente (10 hechos en total, temáticamente correctos). Ambas superaron el tope de 10.000 caracteres:

```
recuperado por el retriever:   21.630 caracteres
llegó al contexto:              2.000  (500 de encabezado + 500 de cola, ×2)
descartado:                    19.630  →  91 %
```

El ranking **no estaba roto**: los hechos recuperados eran los correctos para cada consulta. Lo que fallaba era la **entrega**, y fallaba en silencio: el bloque de memoria aparecía con contenido plausible, y los hechos del medio —hasta cuatro de cada cinco— desaparecían sin aviso.

La causa raíz se verificó contra la composición del almacén: los hechos eran **demasiado grandes para el presupuesto**. Mediana de **688 caracteres**, **54 %** por encima de 600, máximo **3.534**. Cinco hechos de ese tamaño ocupan ~11 KB; el tope de la capa es 10 KB. El propio arnés documenta una expectativa de **147-275 caracteres por entrada**.

**Conclusión de la sección:** el fallo no estaba en la recuperación sino en la **escritura**. Los hechos estaban escritos como documentos.

### 5.4 El mecanismo de depuración existía y estaba apagado

| Componente | Estado medido |
|---|---|
| Similitud léxica (fts) | operativo |
| Similitud por tokens (jaccard) | operativo |
| Similitud vectorial (hrr) | operativo — **256 de 256** hechos con vector |
| `trust_score` | **plano**: 8 valores distintos en 256 hechos; el resto en el default 0,5 |
| `decaimiento` | **apagado**: `media_vida = 0` (no declarado en configuración) |
| `retrieval_count` | **0 en los 256** hechos |

El último renglón merece precisión, porque es donde este trabajo **corrige un error propio**. La lectura inicial del sistema atribuyó el `retrieval_count = 0` a que el agente no ejercía la calibración. La verificación sobre el código completo del arnés mostró otra cosa: **el contador nunca se escribe en ninguna ruta del código**. Está declarado en el esquema y se lee, pero no existe el `UPDATE` que lo incremente. No es una deuda de disciplina del operador: **es una función no implementada**.

Es un error de método con una lección transferible: se reportó como fallo de uso lo que era un fallo de implementación, y se detectó **solo al verificar el código en lugar de confiar en la documentación del propio sistema** (§4.3).

### 5.5 El mantenimiento automático no mantenía nada

El sistema tenía un trabajo programado diario de calibración, con 55 ejecuciones acumuladas y 45 reportes en disco. La revisión de los reportes mostró:

- **0 ajustes aplicados en 27 días consecutivos** (los únicos ajustes reales ocurrieron en los primeros 6 días, sobre el conjunto inicial de 12 hechos).
- El programa **solo escribía un reporte**: no modificaba la base en ningún caso.
- El trabajo estaba **roto hacía 6 días** por un modelo retirado (`failure_streak: 6`, estado `error`), y fallaba en silencio.

Resultado neto: 55 ejecuciones, 45 artefactos y un skill que documentaba el ciclo como operativo, con **cero cambios efectivos** en la base durante 27 de sus corridas. La capa que debía depurarse produjo 45 reportes describiendo que no había nada que depurar, mientras el almacén pasaba de 171 a 256 hechos.

### 5.6 Frecuencia de uso y correcciones: dónde está el fallo recurrente

Sobre el historial completo (1.759 sesiones, 66.559 mensajes) se midió qué temas aparecen y con qué frecuencia, y qué corrige el operador:

| Tema | Sesiones |
|---|---|
| Control de versiones y repositorios | 1.598 |
| Correo | 1.457 |
| Contenido de redes | 1.130 |
| Proyectos y clientes | 636 |
| Skills y herramientas | 612 |
| Wiki y documentación | 535 |
| Sincronización de archivos | 459 |
| Memoria | 349 |

Y de **119 mensajes correctivos** detectados, la clasificación por motivo:

| Motivo de corrección | Casos |
|---|---|
| Ejecutar sin pedir permiso / extrapolar alcance | 37 |
| Formato o estructura del entregable | 31 |
| Memoria: dónde va cada cosa | 27 |
| Verificar antes de afirmar | 23 |
| Adelantarse / hacer de más | 17 |
| No cerrar sin autorización | 17 |
| Tono | 15 |

**El cruce de ambas tablas produce el hallazgo operativo.** Los temas *más frecuentes* son también donde viven las **trampas específicas** —la regla que se olvida y produce un error silencioso—: la herramienta correcta para versionado, el hecho de que el cliente de correo no adjunta archivos, la métrica de longitud de un texto, el alcance real de una compuerta de aprobación. Se verificó el almacén buscando **el hecho específico** de cada trampa:

| Trampa operativa del tema frecuente | ¿Existe el hecho en el almacén? |
|---|---|
| La herramienta correcta de versionado | **No existe** |
| El cliente de correo no adjunta archivos | **No existe** |
| La métrica de longitud de contenido | **No existe** |
| El alcance exacto de la compuerta de aprobación | **No existe** |
| La vía obligatoria de ingesta documental | **No existe** |
| La política de costos frente al cliente | **No existe** |
| La verificación contra el servidor y no contra el disco local | **No existe** |

**Siete de siete trampas de los temas más frecuentes no existían en el almacén.** Estaban —algunas— como entradas de ~200 caracteres apretadas contra el tope del core. La consecuencia es directa: la información que más se necesita **estaba en la capa con menos espacio y sin depuración**, y ausente de la capa diseñada para recuperarla.

### 5.7 Contraste con la práctica publicada

Se revisaron 15 arneses y productos de producción. El hallazgo pertinente para §2.5:

- Solo **dos** publican un límite numérico duro (uno de ellos, este arnés: 2.200 y 1.375 caracteres). La mayoría publica guías cualitativas («mantener bajo N líneas»).
- **Ninguno justifica su límite con medición publicada.**
- La curación documentada tomó una dirección distinta a la consolidación al guardar: uno de los principales productos **eliminó las operaciones de actualización y borrado** de su pipeline, pasando a un modelo de **solo adición** con adjudicación en la lectura, mientras otro **invalida en lugar de borrar**.

Ese último punto refuerza el reparto de este trabajo por una vía inesperada: si la industria está migrando a *no consolidar al escribir*, entonces la consolidación —que es lo único que el core puede hacer— debe reservarse a lo mínimo indispensable.

## 6. Discusión

### 6.1 El diagnóstico en una frase

**El mecanismo estaba bien; el gobierno del contenido no existía.** Las tres causas medidas —hechos-ensayo, tope silencioso de entrega, pesos apagados— tienen en común que ninguna es un defecto de diseño del arnés. Son el resultado de dejar a la deriva **qué entra en cada capa**.

### 6.2 Por qué el archivo de contexto no puede ser la única memoria

Hay tres razones, y conviene separarlas porque la literatura respalda la tercera y **no** la primera:

1. **El costo de lo que se paga siempre no escala.** El historial de adición completa crece cuadráticamente (§2.4). Cualquier capa residente con presupuesto fijo es incompatible con crecimiento ilimitado.
2. **El presupuesto de atención es finito y se mide en reglas, no en tokens.** El cumplimiento decae pasadas 5-6 restricciones simultáneas, y la acumulación es multiplicativa (§2.5). Agregar entradas al core no solo cuesta: **degrada el cumplimiento de las que ya están**.
3. **Sin capa externa no hay política de olvido.** Y la evidencia indica que sin olvido el rendimiento **degrada**: interferencia de asociaciones viejas, acumulación de contradicciones y propagación de memorias falsas (§2.3). Solo una capa externa puede tener decaimiento, invalidación y poda.

La razón que **no** aplica —y conviene declararlo para no atribuirle a la tesis un argumento que no tiene—: **la capa de hechos no es más precisa que el contexto largo**. La comparación publicada favorece al contexto largo en precisión (§2.4). La tesis de este trabajo no depende de ese eje: el argumento es que **cada fuente se invoca cuando se requiere**, no que una sea más certera que otra. El contenido largo y curado tiene su propio destino (el wiki y el corpus de investigación, §3.1) y se consulta por tema; la memoria por hechos cubre lo específico y caducable; y la capa residente queda reducida al residuo sin tema ni caducidad.

Dicho de otro modo: si el contexto largo fuera la única fuente, la consecuencia del resultado de 2603.04814 sería inyectarlo siempre —que es precisamente lo que la evidencia de costo y de densidad de restricciones prohíbe.

### 6.3 Por qué el olvido se delega al almacén externo

Porque **es la única capa donde el olvido puede ser automático y no humano**. El almacén tiene pesos, decaimiento e invalidación; el core tiene un tope que obliga a consolidar a mano, en el mismo turno, con un guard anti-bucle tras 3-4 intentos fallidos.

De ahí se sigue la asimetría que gobierna el reparto:

> **Al core solo puede entrar aquello que no querrías tener que revisar nunca.**

No es una preferencia estética. Es la consecuencia de que el costo de limpiar el core es **tiempo del operador**, mientras el costo de limpiar el almacén es una función del sistema.

### 6.4 La economía de tokens, en concreto

El caso medido da las cifras del argumento:

- El core cuesta **~1.300 tokens fijos por sesión** (2.200 + 1.375 caracteres), se use o no.
- Del contenido del core, **69 %** (9 de 13 entradas, 1.438 de 2.172 caracteres) era datos de dominio que el almacén podía devolver por consulta.
- Recuperar esos datos por consulta cuesta **solo cuando el tema aparece**.
- Y con hechos del tamaño correcto (~150-250 caracteres), cinco hechos recuperados suman **~1.000 caracteres**, **muy por debajo** del tope de 10.000 que hoy se excede.

Es decir: el sistema ya tenía el mecanismo para ser eficiente en la capa externa. Lo que tenía era **hechos escritos en el formato equivocado**, que forzaban el descarte del 91 %.

### 6.5 Qué se sostiene y qué no

**Se sostiene con evidencia de este trabajo:**

- El estado medido de ambas capas (§5.1, §5.4, §5.6), reproducible con los comandos declarados.
- El descarte del 91 % en la entrega del retrieval y su causa raíz en el tamaño de los hechos (§5.3).
- La inexistencia de las 7 trampas operativas en el almacén (§5.6).
- La inefectividad del mantenimiento automático: 0 ajustes en 27 corridas (§5.5).
- Que `retrieval_count` no se escribe en el código (§5.4).

**No se sostiene con los datos de este trabajo, y se declara NO DETERMINABLE:**

- Que el criterio de reparto **mejore la conducta del agente**. Requiere banco de casos con verdad de referencia, que no existe. La comparación pendiente está diseñada pero no ejecutada.
- Que el descarte del 91 % haya causado un fallo conductual concreto. Se midió el mecanismo, no el efecto.
- Que el tamaño de hecho óptimo sea 150-250 caracteres **para este sistema**. Ese número proviene de la documentación del arnés y de la indicación de un cruce medido en **128 tokens** en la literatura de granularidad (§8), no de una medición propia del efecto de tamaño sobre la recuperación en este caso.
- Cualquier generalización a otros arneses.

### 6.6 Conflicto de interés estructural

El autor es el operador del sistema estudiado y el agente que ejecutó las mediciones es el propio sistema medido. Se declaró explícitamente en el diseño que **la entidad medida no puede etiquetar su propio acierto**: por eso las afirmaciones conductuales quedan fuera de alcance en lugar de estimarse. Las mediciones reportadas son de **estado** (conteos, tamaños, distribuciones), verificables por un tercero con los comandos declarados, no de desempeño.

Se documenta además un **error propio detectado durante el trabajo** (§5.4), en el que una afirmación inicial sobre una causa fue refutada al verificar el código, y se incluye porque ilustra el modo de fallo más frecuente de este tipo de análisis: **aceptar la documentación del propio sistema como descripción de su funcionamiento**.

## 7. Amenazas a la validez

### 7.1 Validez de constructo

«Eficiencia de la memoria» se operacionalizó como: uso del presupuesto del core, tamaño de los hechos, proporción de lo recuperado que llega al contexto, y existencia de los hechos operativos. Son indicadores de **forma**, no de **utilidad**. Un sistema puede tener estas métricas correctas y seguir siendo inútil; este trabajo no lo descarta.

### 7.2 Validez interna

Las mediciones son de estado y se tomaron sobre un sistema vivo, sin congelamiento. Se verificaron contra el código y el disco en lugar de contra la documentación. La correlación entre «no existe el hecho» y «el error ocurre» **no se midió**: se establecieron los dos extremos y se dejó la relación como hipótesis.

### 7.3 Validez externa

Muestra de **un** sistema, con un operador, en un arnés concreto y un proveedor de memoria concreto. Los números absolutos (91 %, 54 %, 7 de 7) no son transferibles. El **criterio de reparto** (§4.2) es la parte que se propone como generalizable, y su generalidad tampoco está establecida empíricamente.

### 7.4 Validez de conclusión

Sin grupo de control no hay atribución causal. Las cifras se reportan como descripciones. La medición dependiente del operador (frecuencia de temas, clasificación de correcciones) es **interpretativa** y se declara como tal.

## 8. Trabajo futuro

1. **El banco de casos que falta.** Comparación con verdad de referencia para medir si el criterio mejora la conducta, con variantes léxicas. Diseñada, no ejecutada.
2. **Encender y calibra.** Activar el decaimiento temporal (hoy en cero) y cerrar el ciclo de confianza, una vez instrumentada la lectura. Es la parte de «auto-olvido» que hoy es nominal.
3. **Compactación determinista en la escritura.** Un validador que rechace hechos-ensayo, imperativas y duplicados antes de que entren. La evidencia disponible respalda el enforcement determinista por sobre la instrucción en el prompt.
4. **Medir el tamaño óptimo de hecho.** El cruce de 128 tokens señalado en la literatura de granularidad es una referencia externa; falta la medición propia.
5. **La forma del hecho: atómico contra compuesto.** La literatura se contradice: una línea de trabajo favorece la entrada atómica autocontenida y otra sostiene que **una sola granularidad no alcanza** y propone tres niveles (crudo, atómico, perfil). No resolver sin medir.

## 9. Conclusión

El sistema estudiado tenía dos capas correctas, un ranking de recuperación que acertaba el 100 % de lo que traía, y un mecanismo de decaimiento con la forma que la literatura recomienda. Y sin embargo: el 91 % de lo recuperado no llegaba al contexto, el 54 % de los hechos eran documentos, la mitad del archivo de contexto no le correspondía, y la capa con política de olvido tenía el reloj apagado.

Ninguna de esas fallas se arreglaba mejorando el mecanismo. Todas provienen de lo mismo: **dejar a la deriva qué entra en cada capa**.

La evidencia externa respalda el diagnóstico por tres vías que no se habían coordinado entre sí: un almacén sin compuerta de escritura se derrumba de 97,8 % a 13,3 % con distractores; todos los sistemas evaluados acumulan estado de forma monotónica por defecto; y el olvido es una función cuya ausencia degrada el rendimiento en lugar de ahorrar recursos.

La tesis que este trabajo sostiene es acotada: **el core no puede ser la única memoria** —por costo, por densidad de restricciones y porque sin capa externa no hay olvido—, y **el reparto entre capas se decide por uso y por caducidad, no por contenido**. La parte generalizable es el criterio. La parte honesta es que su efecto sobre la conducta sigue sin medirse.

## Referencias

### Verificadas por extracción directa del recurso

- **Zahn, O. & Chana, J.** (2026). *Selective Memory for Artificial Intelligence: Write-Time Gating with Hierarchical Archiving.* arXiv:2603.15994. [Verificado por extracción]
- **Pollertlam, N. et al.** (2026). *Beyond the Context Window: A Cost-Performance Analysis of Fact-Based Memory vs. Long-Context LLMs for Persistent Agents.* arXiv:2603.04814, cs.CL, 5-mar-2026. [Verificado por extracción]
- **Fofadiya, P. & Tiwari, S.** (2026). *Novel Memory Forgetting Techniques for Autonomous AI Agents: Balancing Relevance and Efficiency.* arXiv:2604.02280, cs.AI, 2-abr-2026. [Verificado por extracción]
- **Rana, A. et al.** (2026). *Oblivion: Self-Adaptive Agentic Memory Control through Decay-Driven Activation.* arXiv:2604.00131v2, cs.CL, 31-mar-2026 / 17-abr-2026. [Verificado por extracción]
- **Du, P.** (2026). *Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers.* arXiv:2603.07670, cs.AI, 8-mar-2026. [Verificado por extracción]
- **Dadhich, G.** (2026). *Agentic Context Management: Solving Agent Memory and Cost by Treating Them as Lifecycle and Architecture Problems.* arXiv:2607.21503, cs.AI, 23-jul-2026. [Verificado por extracción]
- **Chen, Z. & Cheng, Q.** (2026). *Learning What to Remember: A Cognitively Grounded Multi-Factor Value Model for Agentic Memory.* arXiv:2606.12945, 11-jun-2026. [Verificado]
- **Sidik, B. et al.** (2026). *MEMTIER: Tiered Memory Architecture and Retrieval Bottleneck Analysis for Long-Running Autonomous Agents.* arXiv:2605.03675, 5-may-2026. [Verificado]
- (2026). *Agent Memory: Characterization and System Implications of Stateful Long-Horizon Workloads.* arXiv:2606.06448, 4-jun-2026. [Verificado]
- **Yu, C. et al.** (2026). *The Hidden Footprint: Making Storage a First-Class Metric for LLM Agent Evaluation.* arXiv:2607.11149, 13-jul-2026. [Verificado]
- (2026). *MemRefine: LLM-Guided Compression for Long-Term Agent Memory.* arXiv:2606.13177, 11-jun-2026. [Verificado]
- **Zhong, W. et al.** (2024). *MemoryBank: Enhancing Large Language Models with Long-Term Memory.* arXiv:2305.10250 (AAAI 2024). [Verificado]
- **Packer, C. et al.** (2024). *MemGPT: Towards LLMs as Operating Systems.* [Citado vía relevamiento 2603.07670]
- **Vasileva, A.** (2026). *Large Language Models Can Follow Instructions, But Not Many at Once.* arXiv:2608.12426. [Verificado en el ciclo previo del proyecto]

### Fuentes internas del sistema estudiado

- Documentación del arnés Hermes sobre memoria (`user-guide/features/memory`), proveedores de memoria (`memory-providers`) y guía de memoria del prompt de sistema.
- Código del proveedor holográfico y del gestor de memoria del arnés, leído para verificar §3.2, §3.3 y §5.4.
- Archivos de volcado de `hook_outputs/` de la sesión medida (§5.3).
- Base de conocimiento local del proyecto: cuatro documentos de investigación del ciclo 2026-09-28 sobre memoria (`papers-politicas-escritura`, `arneses-comparados`, `evidencia-efectividad`, `intervenciones-efectivas`).

### Referenciadas por resumen o cita secundaria — verificar antes de envío

- Las cifras de producto de proveedores comerciales de memoria, marcadas como autodeclaradas y **no reproducidas** en este trabajo.

## Agradecimientos

Al operador del sistema, por sostener empíricamente la tesis del reparto antes de que existiera evidencia que la respaldara, y por exigir que la medición se hiciera contra el sistema real y no contra su documentación.

## Declaración de uso de IA generativa

Las mediciones, la verificación de fuentes y la redacción de este borrador fueron ejecutadas por el propio agente del sistema estudiado, con supervisión y dirección del autor. Esta circunstancia se declara como conflicto de interés estructural en §6.6. Todas las referencias externas fueron verificadas por extracción directa del recurso; ninguna cifra se reporta por cita secundaria sin marcarlo.

## Apéndice A — Mediciones crudas

| Medición | Valor |
|---|---|
| Sesiones en el historial | 1.759 |
| Mensajes totales | 66.559 |
| Entradas en `MEMORY.md` | 13 |
| Uso del presupuesto del core | 2.172 / 2.200 caracteres (98 %) |
| Entradas del core que son datos de dominio | 9 de 13 (69 %) |
| Entradas del core que solapan ≥50 % con el almacén | 5 de 13 |
| Hechos en el almacén | 256 |
| Mediana de tamaño de hecho | 688 caracteres |
| Hechos por encima de 600 caracteres | 137 (54 %) |
| Hecho más grande | 3.534 caracteres |
| Recuperado por `prefetch` (2 corridas) | 21.630 caracteres |
| Llegó al contexto | 2.000 caracteres |
| Descartado | 19.630 caracteres (91 %) |
| Hechos con `retrieval_count > 0` | **0 de 256** |
| Valores distintos de `trust_score` | 8 en 256 hechos |
| Media de vida del decaimiento | 0 (apagado) |
| Corridas del mantenimiento automático | 55 |
| Ajustes aplicados en 27 días consecutivos | 0 |
| Trampas operativas ausentes del almacén | 7 de 7 |
| Mensajes correctivos detectados | 119 |

## Apéndice B — Verificación de identificadores

Los trece identificadores arXiv citados fueron verificados abriendo el recurso y contrastando título, autoría y fecha de sometimiento:

| ID | Título verificado | Fecha |
|---|---|---|
| 2603.04814 | Beyond the Context Window: A Cost-Performance Analysis of Fact-Based Memory vs. Long-Context LLMs… | 5-mar-2026 |
| 2603.07670 | Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers | 8-mar-2026 |
| 2603.15994 | Selective Memory for Artificial Intelligence: Write-Time Gating with Hierarchical Archiving | 16-mar-2026 |
| 2604.00131 | Oblivion: Self-Adaptive Agentic Memory Control through Decay-Driven Activation | 31-mar-2026 |
| 2604.02280 | Novel Memory Forgetting Techniques for Autonomous AI Agents… | 2-abr-2026 |
| 2605.03675 | MEMTIER: Tiered Memory Architecture and Retrieval Bottleneck Analysis… | 5-may-2026 |
| 2606.06448 | Agent Memory: Characterization and System Implications of Stateful Long-Horizon Workloads | 4-jun-2026 |
| 2606.12945 | Learning What to Remember: A Cognitively Grounded Multi-Factor Value Model for Agentic Memory | 11-jun-2026 |
| 2606.13177 | MemRefine: LLM-Guided Compression for Long-Term Agent Memory | 11-jun-2026 |
| 2607.11149 | The Hidden Footprint: Making Storage a First-Class Metric for LLM Agent Evaluation | 13-jul-2026 |
| 2607.21503 | Agentic Context Management: Solving Agent Memory and Cost… | 23-jul-2026 |
| 2305.10250 | MemoryBank: Enhancing Large Language Models with Long-Term Memory | AAAI 2024 |
| 2608.12426 | Large Language Models Can Follow Instructions, But Not Many at Once | verificado en ciclo previo |

**No verificado y marcado como tal:** las cifras autodeclaradas de proveedores comerciales de memoria (§2.4, §5.7), y la comparación de precisión publicada por los propios productos.

## Apéndice C — Checklist de reproducibilidad

1. Composición del core: leer `MEMORY.md` y `USER.md`, contar entradas separadas por el delimitador y medir caracteres.
2. Composición del almacén: consultar la tabla `facts` — número, distribución de tamaños, valores de `trust_score`, `retrieval_count`.
3. Parámetros de depuración: leer la configuración del proveedor y verificar `temporal_decay_half_life`.
4. Comportamiento de la entrega: listar `hook_outputs/<sesión>/` y comparar los caracteres recuperados contra los inyectados.
5. Cobertura del criterio: cotejar cada entrada del core contra los hechos por solape de tokens.
6. Frecuencia de uso y correcciones: consultar el historial por patrón sobre los mensajes del operador.
7. Ausencia de las trampas: buscar en el almacén el hecho específico de cada trampa, no un hecho relacionado.

## Apéndice D — Inventario de evidencia

| Evidencia | Origen | Verificación |
|---|---|---|
| Estado de las dos capas | Sistema en producción | Consultas SQLite y lectura de archivos |
| Comportamiento del retrieval | Volcados de `hook_outputs/` | Lectura directa de los archivos |
| Tope y previsualización | Código del arnés | Lectura del módulo de volcado |
| Función no implementada | Código del proveedor | Búsqueda global del contador |
| Mantenimiento inefectivo | 45 reportes en disco + registro del trabajo | Lectura de reportes y estado del trabajo |
| Frecuencia y correcciones | Historial de sesiones | Consulta por patrón |
| Prácticas publicadas | Documentación de 15 productos | Extracción directa |

## Apéndice E — Advertencia de lectura

Este trabajo reporta mayoritariamente **resultados negativos**: mecanismos correctos que no operaban, automatizaciones que no automatizaban, y una capa de recuperación que descartaba casi todo lo que traía. Se incluye el error propio de §5.4 porque el objetivo del documento no es acreditar el sistema ni al operador, sino **documentar con precisión un modo de fallo que parece invisible desde dentro**: el sistema informaba un estado plausible y el agente no tenía forma de saber qué se había descartado.

La sección de límites (§6.5) es parte del aporte, no un anexo defensivo. Las tres afirmaciones que **no** se sostienen están enumeradas ahí con el mismo énfasis que las que sí.
