#!/usr/bin/env python3
"""Alimentacion de la memoria holografica desde el compresor de compactacion.

PARTE DEL REPO hermes-hollomem-helper, pero NO es el plugin. El plugin
(holographic, bundled) solo recupera; este script ESCRIBE. Se ejecuta como cron
no_agent: subprocess sin LLM del arnes, costo 0 en el agente principal.

POR QUE EL COMPRESOR Y NO EL TURNO CRUDO
Medido en esta sesion: los resumenes de compactacion dan hay_hecho 0.78-0.87 vs
0.11-0.73 de los turnos sueltos, SIN SOLAPAMIENTO. Ademas cuestan 98 tok por
candidato contra 311, y traen 120 candidatos por sesion contra ~8 del turno
suelto. Y resuelven la consolidacion: los resumenes ya fusionaron los duplicados
que el turno aislado produce.

EL CIRCUITO
  1. lee de state.db los bloques [CONTEXT COMPACTION] nuevos (id > ultimo visto)
  2. extrae candidatos: lineas de las secciones del resumen
  3. JEV decide: hay_hecho / es_efimero / es_procedimiento   (~0.5 s c/u)
  4. las reglas deterministas ANOTAN, no descartan
  5. redacta el hecho (LLM, <=275 chars)
  6. escribe con add_fact real + trust 0.35 + 0.30*P
  7. watchdog del prefetch: verifica que el plugin siga inyectando hechos

POR QUE LAS REGLAS ANOTAN Y NO FILTRAN (medido fuera de muestra, 616 candidatos)
  falso negativo: 118 candidatos -> JEV los descarta igual. NO pierde hechos.
  falso positivo:  75 candidatos -> 13 valian la pena. SE PIERDEN sin que JEV los vea.
  El filtro costaba 13 hechos para ahorrar 134 s = 10 s por hecho perdido.
  Y los que mata son los MEJOR documentados: llevan un numero (Ley 186/2020), una
  fecha o una extension, y por eso se activa la regla. El dato que da valor es el
  que dispara el descarte.

ESTADO: ~/.hermes/plugin-data/hermes-hollomem-helper/ (NUNCA en el repo ni en
<home>/plugins/<name>/, que el host borra al actualizar).

USO
  python3 alimentar.py                 # dry-run: dice que haria, no escribe
  python3 alimentar.py --escribir      # escribe de verdad
  python3 alimentar.py --desde-chars 0 # re-procesa todo desde el primer bloque
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERMES = Path("/home/andrea/.hermes")
STATE = HERMES / "state.db"
MEM = HERMES / "memory_store.db"
HOLO = HERMES / "hermes-agent" / "plugins" / "memory" / "holographic"
ESTADO = HERMES / "plugin-data" / "hermes-hollomem-helper"
ESTADO.mkdir(parents=True, exist_ok=True)
PROGRESO = ESTADO / "ultimo_bloque.json"
LOG = ESTADO / "alimentar.log"

JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "~typesafe/jev-latest"
REDACTOR = "deepseek/deepseek-v4.1-flash"

# El redactor es un modelo de RAZONAMIENTO: el campo `reasoning` consume el
# max_tokens. Con 400 y 1500 devolvia 0 chars. Con 3000 devuelve ~275.
MAX_TOKENS_REDACCION = 3000
LARGO_MAX_HECHO = 275

SECCIONES_RICAS = {
    "Key Decisions", "Errors & Fixes", "Resolved Questions",
    "Constraints & Preferences", "Critical Context", "Active State",
    "Blocked", "Lessons", "Hallazgos",
}

PREGUNTAS = {
    # CORREGIDO (medido: 0/6 -> 6/6 sobre las Constraints & Preferences). La
    # version anterior decia "NO es una instruccion", y los candidatos mas
    # valiosos del resumen de compactacion SON citas de instrucciones y
    # correcciones de Mauro. JEV las leia literalmente y las rechazaba: el
    # 100% de las reglas de trabajo se estaba perdiendo. Lo que importa no es
    # la FORMA (orden, cita, correccion) sino si describe algo PERMANENTE.
    "hay_hecho": ("El texto revela algo DURADERO sobre una persona, un sistema o una "
                  "regla de trabajo que conviene recordar para no repetir un error. "
                  "CUENTA COMO HECHO aunque este redactado como una orden, una "
                  "correccion o una cita textual: lo que importa es si describe algo "
                  "permanente. NO cuenta si es el estado momentaneo de una tarea en "
                  "curso, una lista de archivos, o un detalle que cambia pronto."),
    "es_efimero": ("El contenido depende de algo que PUEDE CAMBIAR PRONTO y por eso "
                   "deja de ser cierto: una ruta o un archivo de esta maquina, un PID, "
                   "un hash, un conteo de tests, una version, una rama de git, el "
                   "estado de una tarea en curso, un pendiente, una cifra de gestion."),
    "es_procedimiento": ("El contenido ensena COMO hacer algo: una secuencia de pasos, "
                         "un runbook, una tecnica. Va a un skill, no a un hecho."),
    "contradice_existente": ("El HALLAZGO contradice o invalida el HECHO EXISTENTE: "
                             "afirma algo incompatible, lo niega, o lo vuelve obsoleto. "
                             "NO si solo agrega detalle o confirma lo mismo con otras "
                             "palabras."),
}

# Reglas ANOTADORAS. No descartan: etiquetan. Medido 70.2% precision / 60.1%
# recall fuera de muestra -> suficiente para anotar, insuficiente para filtrar.
REGLAS = [
    ("ruta_absoluta", r"(?:^|\s)~(?:/|\b)|/home/|/tmp/|/var/|/etc/|/usr/"),
    ("archivo_con_extension", r"\b[\w.-]+\.(?:py|js|ts|json|yaml|yml|md|db|log|sh|toml|cfg|ini|txt)\b"),
    ("pid", r"\bPID\b|\bpid\s*\d+"),
    ("hash_commit", r"\b[0-9a-f]{7,40}\b(?![0-9a-f])|commit\s+`?[0-9a-f]{6,}"),
    ("version", r"\bv?\d+\.\d+\.\d+\b"),
    ("conteo_tests", r"\b\d+/\d+\s*(?:tests?|pasando)|\b\d+\s*tests?\b"),
    ("rama_git", r"\brama\s+`?[\w./-]+|\b(?:main|master|develop)\b"),
    ("fecha", r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}-(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"),
    ("linea_codigo", r"\.py:\d+|:\d{2,5}\b|línea\s+\d+"),
    ("conteo_cantidad", r"\b\d{2,}\s*(?:chars|bytes|KB|MB|tok|tokens)\b|\b\d+\s*(?:skills|facts|entradas)\b"),
    ("estado_pendiente", r"\bpendiente\b|\ben curso\b|\besta sesión\b|\bahora mismo\b|\bpor hacer\b"),
    ("comando_cli", r"`hermes\s+\w+|\bhermes\s+(?:plugins|memory|cron|skills)\b"),
    ("cifra_de_gestion", r"\b\d{2,}\s*(?:pendings?|hechos?|bloques?|líneas?|mensajes?)\b"),
]
RX = [(n, re.compile(p, re.I)) for n, p in REGLAS]

BLOQUE_RX = re.compile(r"\[CONTEXT COMPACTION[^\]]*\]", re.I)


def log(msg: str) -> None:
    """Va SIEMPRE al archivo de log. A consola solo si es ruidoso (--verbose) o
    dry-run: como cron no_agent, el stdout se entrega verbatim al usuario, asi que
    el detalle no debe salir por ahi."""
    linea = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass
    if VERBOSO or DRY:
        print(linea, flush=True)


VERBOSO = False
DRY = False


def avisar(msg: str) -> None:
    """Lo unico que sale por stdout en modo cron: el resumen que Mauro ve."""
    print(msg, flush=True)


# ------------------------------------------------------------------ credencial
def _cargar_env() -> None:
    p = HERMES / ".env"
    if not p.exists():
        return
    for l in p.read_text(errors="ignore").splitlines():
        s = l.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_cache_clave: dict[str, str | None] = {}


def clave(nombre: str) -> str | None:
    if nombre in _cache_clave:
        return _cache_clave[nombre]
    _cargar_env()
    v = os.environ.get(nombre)
    if not v:
        sys.path.insert(0, str(HERMES / "scripts"))
        try:
            from infisical_auth import get_secret
            v = get_secret(nombre)
        except Exception as e:
            log(f"  credencial {nombre}: infisical fallo ({str(e)[:60]})")
            v = None
    _cache_clave[nombre] = str(v) if v else None
    return _cache_clave[nombre]


# ------------------------------------------------------------------ JEV
def jev_responder(state: dict, questions: dict, api_key: str, intentos: int = 3) -> dict | None:
    body = {"model": JEV_MODEL, "state": state,
            "questions": {k: {"type": "noul", "instructions": v} for k, v in questions.items()}}
    req = urllib.request.Request(
        JEV_ENDPOINT, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                ans = json.load(r).get("answers", {})
            return {k: (ans.get(k, {}) or {}).get("noul") for k in questions}
        except Exception as e:
            if i == intentos - 1:
                log(f"  JEV fallo: {str(e)[:100]}")
                return None
            time.sleep(2)
    return None


# ------------------------------------------------------------------ redaccion
def redactar(candidato: str, api_key: str, seccion: str) -> str | None:
    """Un hecho, <=275 chars, sin adornos. Se le da el criterio medido en la sesion
    ('un hecho es algo cuya ausencia ya costo un error')."""
    prompt = (
        "Convierte este hallazgo en UN hecho memorizable, en espanol. Maximo 275 "
        "caracteres. Sin preambulo, sin comillas, sin markdown. Un solo parrafo.\n\n"
        "Reglas de redaccion:\n"
        "- Tercera persona si es sobre un sistema. Primera persona femenina solo si "
        "es sobre Andrea: 'Andrea hace X', no 'Estoy convencida de que...'.\n"
        "- El hecho AFIRMA la regla o el dato. NO narra el incidente ni agrega por "
        "que se aprendio. Prohibido terminar con 'ya fallo', 'ya costo un error', "
        "'sin eso se equivoca', o cualquier justificacion. Solo el hecho.\n"
        "- No incluyas rutas, PIDs, hashes, versiones ni conteos que cambian pronto: "
        "si el hallazgo depende de uno, redacta lo esencial sin ese dato.\n\n"
        "Ejemplo de lo que NO se quiere:\n"
        "  'Necesito tablas de valores crudos para evaluar; sin ellas ya falle.'\n"
        "Ejemplo de lo que SI se quiere:\n"
        "  'Mauro exige tablas y valores crudos al evaluar un resultado; los "
        "resumenes de opinion no le sirven.'\n\n"
        "Hallazgo (seccion del resumen: " + seccion + "):\n" + candidato[:1800]
    )
    body = {"model": REDACTOR, "max_tokens": MAX_TOKENS_REDACCION,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    for i in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = (json.load(r)["choices"][0]["message"].get("content") or "").strip()
            if not txt:
                return None
            txt = re.sub(r"^[\"'`]+|[\"'`]+$", "", txt).strip()
            txt = re.sub(r"\s+", " ", txt)
            return txt[:LARGO_MAX_HECHO]
        except Exception as e:
            if i == 1:
                log(f"  redaccion fallo: {str(e)[:90]}")
                return None
            time.sleep(2)
    return None


# ------------------------------------------------------------------ candidatos
def candidatos_de(texto: str) -> list[dict]:
    out = []
    for parte in re.split(r"(?m)^##\s+", texto)[1:]:
        titulo = parte.split("\n", 1)[0].strip()
        cuerpo = parte.split("\n", 1)[1] if "\n" in parte else ""
        for m in re.finditer(r"(?m)^\s*[-*]\s+(.+)$", cuerpo):
            t = m.group(1).strip()
            if len(t) >= 45:
                out.append({"seccion": titulo, "texto": t,
                            "seccion_rica": titulo in SECCIONES_RICAS})
    return out


def marcas(t: str) -> list[str]:
    return [n for n, r in RX if r.search(t)]


def huella(t: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", t.strip().lower())[:400].encode()).hexdigest()[:16]


# ------------------------------------------------------------------ store
def cargar_store():
    """Carga el MemoryStore y el FactRetriever del PAQUETE holographic (no el
    modulo suelto: sus imports relativos fallan). Debe ser el paquete tambien
    porque search() vive en el retriever y add_fact() en el store; y add_fact
    real es obligatorio: un INSERT crudo NO extrae entidades ni vector HRR."""
    spec = importlib.util.spec_from_file_location(
        "hollomem_runtime", HOLO / "__init__.py",
        submodule_search_locations=[str(HOLO)])
    if spec is None or spec.loader is None:
        raise RuntimeError(f"no pude cargar el paquete holographic desde {HOLO}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hollomem_runtime"] = mod
    spec.loader.exec_module(mod)
    from hollomem_runtime.retrieval import FactRetriever
    from hollomem_runtime.store import MemoryStore
    store = MemoryStore(db_path=str(MEM), default_trust=0.5)
    return store, FactRetriever(store)


# ------------------------------------------------------------------ progreso
def leer_progreso() -> dict:
    if PROGRESO.exists():
        try:
            return json.loads(PROGRESO.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"bloques_completos": [], "ultima_corrida": None, "huellas": []}


def guardar_progreso(p: dict) -> None:
    p["ultima_corrida"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = PROGRESO.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROGRESO)


# ------------------------------------------------------------------ watchdog
def watchdog_prefetch(st: sqlite3.Connection) -> dict:
    """Verifica que el plugin siga inyectando hechos.

    Es un fallo SILENCIOSO por diseno: prefetch() atrapa la excepcion con
    logger.debug y devuelve ''. El nivel debug no se escribe (0 lineas en
    agent.log), asi que si empezara a fallar no habria rastro. El unico lugar
    donde queda constancia es messages.api_content, que guarda lo que se envio
    al modelo."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    q = """SELECT api_content FROM messages
           WHERE role='user' AND api_content LIKE '%## Holographic Memory%'
             AND date(timestamp,'unixepoch','localtime') = ?"""
    filas = st.execute(q, (hoy,)).fetchall()
    con_hechos = 0
    for f in filas:
        m = re.search(r"## Holographic Memory\n(.*?)</memory-context>", f[0] or "", re.S)
        if m and any(l.strip().startswith("- [") for l in m.group(1).splitlines()):
            con_hechos += 1
    return {"turnos_hoy": len(filas), "turnos_con_hechos": con_hechos,
            "ok": len(filas) == 0 or con_hechos > 0}


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--escribir", action="store_true", help="escribe de verdad (sin esto: dry-run)")
    ap.add_argument("--verbose", action="store_true", help="detalle a consola")
    ap.add_argument("--max-candidatos", type=int, default=120)
    ap.add_argument("--max-juegos", type=int, default=60, help="tope de llamadas a JEV")
    args = ap.parse_args()

    global VERBOSO, DRY
    VERBOSO = args.verbose or not args.escribir
    DRY = not args.escribir

    t0 = time.monotonic()
    log("=" * 68)
    log(f"alimentacion de facts — {'ESCRITURA' if args.escribir else 'DRY-RUN'}")

    prog = leer_progreso()
    huellas = set(prog.get("huellas", []))
    log(f"  huellas recordadas: {len(huellas)}")

    st = sqlite3.connect(f"file:{STATE}?mode=ro", uri=True)
    st.row_factory = sqlite3.Row

    # ---- watchdog siempre, cueste lo que cueste: es la red de seguridad
    wd = watchdog_prefetch(st)
    log(f"  watchdog prefetch: {wd['turnos_con_hechos']}/{wd['turnos_hoy']} turnos de hoy "
        f"con hechos inyectados -> {'OK' if wd['ok'] else 'ALERTA: la inyeccion no esta saliendo'}")
    if not wd["ok"]:
        log("  !! el prefetch no inyecta hechos. Revisar antes de seguir.")

    # ---- bloques a procesar
    # NO un cursor monotono: con topes, un cursor saltea lo que no alcanzo a
    # procesarse (y se pierde para siempre). Se lleva una LISTA de bloques ya
    # completados; los que quedaron a medias no entran en la lista y se releen.
    # Las huellas evitan reprocesar sus candidatos.
    hechos_ids = set(prog.get("bloques_completos", []))
    filas = st.execute("""SELECT id, session_id, content FROM messages
                          WHERE content LIKE '[CONTEXT COMPACTION%'
                          ORDER BY id DESC LIMIT 60""").fetchall()
    filas = [f for f in filas if f["id"] not in hechos_ids]
    log(f"  bloques de compactacion pendientes: {len(filas)} "
        f"({len(hechos_ids)} ya completados en corridas previas)")
    if not filas:
        log("  nada nuevo. Fin.")
        guardar_progreso(prog)
        return 0

    # ---- candidatos
    # BUG que se corrige aca: avanzar el cursor al ultimo bloque leido PIERDE los
    # candidatos que el tope dejo sin procesar (no vuelven a mirarse nunca). El
    # cursor avanza solo hasta el ultimo bloque COMPLETO; los incompletos se
    # releen en la proxima corrida y el filtro de huellas evita repetir trabajo.
    pendientes, descartados, bloques_completos = [], 0, []
    for f in filas:
        cs = candidatos_de(f["content"])
        if not cs:
            bloques_completos.append(f["id"])
            continue
        for c in cs:
            c["msg_id"] = f["id"]
            h = huella(c["texto"])
            if h in huellas:
                descartados += 1
                continue
            c["huella"] = h
            pendientes.append(c)
    # prioriza lo mas RECIENTE y las secciones ricas: el backlog historico se
    # drena en varias corridas, y lo nuevo importa mas que lo viejo
    pendientes.sort(key=lambda c: (not c["seccion_rica"], -c["msg_id"]))
    recortados = max(0, len(pendientes) - args.max_candidatos)
    pendientes = pendientes[:args.max_candidatos]
    log(f"  candidatos: {len(pendientes)} pendientes"
        f"{f' ({descartados} ya vistos)' if descartados else ''}"
        f"{f' ({recortados} quedan para la proxima)' if recortados else ''}")

    k_openrouter = clave("OPENROUTER_API_KEY")
    if not k_openrouter:
        log("  !! sin OPENROUTER_API_KEY: no puedo llamar a JEV ni al redactor. Fin.")
        return 1

    # ---- compuerta JEV sobre el candidato (individual: ahi SI discrimina 0.04-0.81)
    aprobados, rechazos = [], []
    for i, c in enumerate(pendientes, 1):
        if len(aprobados) + len(rechazos) >= args.max_juegos:
            log(f"  tope de {args.max_juegos} juicios alcanzado; el resto espera la proxima corrida")
            break
        r = jev_responder({"candidato": c["texto"][:6000]}, {
            "hay_hecho": PREGUNTAS["hay_hecho"],
            "es_efimero": PREGUNTAS["es_efimero"],
            "es_procedimiento": PREGUNTAS["es_procedimiento"],
        }, k_openrouter)
        if not r:
            continue
        c["jev"] = r
        c["marcas"] = marcas(c["texto"])   # ANOTACION, no descarte
        if (r.get("hay_hecho") or 0) >= 0.5 and (r.get("es_procedimiento") or 0) < 0.5:
            aprobados.append(c)
        else:
            rechazos.append(c)
        if i % 20 == 0:
            log(f"    ...{i}/{len(pendientes)}  aprobados={len(aprobados)}")

    log(f"  compuerta JEV: {len(aprobados)} aprobados / {len(rechazos)} rechazados")
    # las marcas quedan registradas aunque el candidato se rechace: es la
    # segunda opinion que permite revisar el umbral sin depender de juicio humano
    if rechazos:
        con_marca = [c for c in rechazos if c["marcas"]]
        log(f"  discrepancia registrada: {len(con_marca)} rechazados que las reglas SI marcan")

    # ---- redaccion
    hechos = []
    for c in aprobados:
        txt = redactar(c["texto"], k_openrouter, c["seccion"])
        if not txt:
            continue
        p = c["jev"].get("hay_hecho") or 0.0
        hechos.append({**c, "redactado": txt, "trust": round(min(0.65, 0.35 + 0.30 * p), 3)})
    log(f"  redactados: {len(hechos)}")

    # ---- escritura
    escritos = fusionados = contradictorios = 0
    if args.escribir:
        store, retriever = cargar_store()
        for h in hechos:
            # ¿contradice algo existente? (JEV lo resuelve 8/8 donde contradict() da 0/4)
            previos = retriever.search(h["redactado"], min_trust=0.3, limit=3)
            contradijo = False
            for pv in previos:
                chk = jev_responder(
                    {"hecho_existente": pv["content"][:3000], "hallazgo_nuevo": h["redactado"][:3000]},
                    {"contradice_existente": PREGUNTAS["contradice_existente"]}, k_openrouter)
                # Umbral 0.7: medido en esta sesion, JEV separa contradicciones
                # reales en 0.88-0.97 y controles en 0.04-0.12, sin solapamiento.
                # Con 0.5 se detenian pares COMPLEMENTARIOS (el .env no es secreto
                # vs los secretos viven en Infisical: ambas ciertas). Detener de
                # mas cuesta un hecho; detener de menos cuesta una creencia vieja.
                if chk and (chk.get("contradice_existente") or 0) >= 0.7:
                    contradijo = True
                    contradictorios += 1
                    log(f"    CONTRADICE #{pv['fact_id']} ({chk['contradice_existente']:.2f}): "
                        f"{h['redactado'][:60]}")
                    log(f"      existente: {pv['content'][:60]}")
                    break
            if contradijo:
                # NO se escribe sola: se deja propuesta para Mauro. La memoria no
                # se reescribe por si misma una creencia sobre el mundo.
                continue
            if previos and previos[0].get("score", 0) > 0.75:
                store.record_feedback(previos[0]["fact_id"], helpful=True)  # refuerza, no duplica
                fusionados += 1
                continue
            fid = store.add_fact(h["redactado"], category="general")
            store.update_fact(fid, trust_delta=h["trust"] - 0.5)  # add_fact entra en default 0.5
            escritos += 1
            log(f"    + #{fid} trust={h['trust']:.2f} [{','.join(h['marcas']) or 'sin marcas'}] "
                f"{h['redactado'][:58]}")
        store._conn.close()
        log(f"  escritura: {escritos} nuevos, {fusionados} reforzados, "
            f"{contradictorios} detenidos por contradiccion")
    else:
        log("  DRY-RUN — esto es lo que se escribiria:")
        for h in hechos[:25]:
            log(f"    trust={h['trust']:.2f} h={h['jev']['hay_hecho']:.2f} "
                f"[{','.join(h['marcas']) or 'sin marcas'}]")
            log(f"      {h['redactado'][:120]}")

    # ---- progreso
    # BUG que se corrige aca: `pendientes` incluye candidatos que el tope de
    # juicios dejo SIN EVALUAR. Si sus huellas se marcan como vistas, nunca se
    # re-evaluan y se pierden para siempre. `procesadas` son solo las huellas
    # que REALMENTE pasaron por JEV; y un bloque entra en `bloques_completos`
    # solo si TODOS sus candidatos fueron evaluados (no solo vistos).
    evaluadas = huellas | {c["huella"] for c in aprobados + rechazos}
    sin_evaluar = len(pendientes) - len(aprobados) - len(rechazos)
    completos = [f["id"] for f in filas
                 if all(huella(c["texto"]) in evaluadas for c in candidatos_de(f["content"]))]
    prog["bloques_completos"] = sorted(hechos_ids | set(completos))[-2000:]
    prog.pop("ultimo_msg_id", None)  # el cursor monotono ya no se usa
    prog["huellas"] = list(evaluadas)[-4000:]
    if sin_evaluar:
        log(f"  {sin_evaluar} candidato(s) sin evaluar: vuelven en la proxima corrida "
            f"(no se marcan como vistos)")
    prog.setdefault("historial", []).append({
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modo": "escritura" if args.escribir else "dry-run",
        "bloques": len(filas), "candidatos": len(pendientes),
        "aprobados": len(aprobados), "redactados": len(hechos),
        "watchdog": wd,
    })
    prog["historial"] = prog["historial"][-200:]
    guardar_progreso(prog)

    log(f"listo en {time.monotonic()-t0:.0f}s")

    # ---- lo unico que sale por stdout en modo cron (no_agent entrega verbatim).
    # Si no hay nada que reportar, NO se imprime: el cron no manda nada.
    if args.escribir:
        partes = []
        if escritos:
            partes.append(f"{escritos} hecho(s) nuevo(s)")
        if fusionados:
            partes.append(f"{fusionados} reforzado(s)")
        if contradictorios:
            partes.append(f"{contradictorios} detenido(s) por contradiccion")
        if not wd["ok"]:
            partes.append(f"ALERTA: el prefetch no inyecto hechos hoy "
                          f"({wd['turnos_con_hechos']}/{wd['turnos_hoy']} turnos)")
        if partes:
            avisar(f"Memoria holografica: " + ", ".join(partes) + ".")
            if contradictorios:
                avisar("Revisar los detenidos: contradicen un hecho existente y no "
                       "se reescriben solos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
