# gym-coach

Entrenador personal asistido por IA con sincronización Hevy, métricas deterministas, entrevista
longitudinal y propuestas estructuradas. Toda aplicación de rutina exige una confirmación final sobre
una preview exacta.

## Requisitos e instalación

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker Compose (para PostgreSQL; Ollama es experimental y opcional)
- Hevy Pro y una API key para los comandos reales de sincronización

```bash
uv sync
cp .env.example .env
# Edita .env localmente y define las claves necesarias; no las pegues en logs ni en Git.
docker compose up -d postgres
```

PostgreSQL usa `restart: unless-stopped`, por lo que vuelve a arrancar cuando Docker Desktop
se inicia. En Docker Desktop activa también “Start Docker Desktop when you sign in”. Ollama está
en el perfil opcional `llm` y no se inicia con el comando anterior; actívalo solo si se necesita:

```bash
docker compose --profile llm up -d ollama
```

`HEVY_API_KEY` solo es necesaria para comprobar o sincronizar Hevy. El servidor MCP y las consultas
normalizadas no requieren claves de modelos. `OPENAI_API_KEY` pertenece únicamente a la integración
PydanticAI experimental.

## Ejecución

```bash
uv run uvicorn gym_coach.main:app --reload
curl http://127.0.0.1:8000/health

uv run gym-coach hevy check
uv run gym-coach hevy user
uv run gym-coach hevy routines
uv run gym-coach hevy workouts --limit 20
uv run gym-coach hevy exercise-templates
uv run alembic upgrade head
uv run gym-coach hevy sync
uv run gym-coach metrics summary --days 28 --target-sessions 4
uv run gym-coach metrics exercise EXERCISE_TEMPLATE_ID --days 180
uv run gym-coach mcp

uv run gym-coach coach profile-set --experience intermediate --days 4 --minutes 60 \
  --equipment "gimnasio completo"
uv run gym-coach coach goal-add --type hypertrophy \
  --description "Ganar masa muscular manteniendo cuatro sesiones semanales" --priority 1
# Experimental: requiere `uv sync --extra pydanticai`
uv run gym-coach coach ask "Revisa mis rutinas y propón mejoras justificadas"
uv run gym-coach coach proposals
uv run gym-coach coach approve PROPOSAL_UUID
# También disponible: coach reject PROPOSAL_UUID
```

Cada respuesta original se escribe bajo `data/raw/hevy/` para depuración. El directorio está
ignorado por Git y puede contener datos personales. Los comandos nunca muestran la API key.

## Calidad

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

## Arquitectura inicial

```text
src/gym_coach/
├── api/                  # routers HTTP, sin lógica de proveedor
├── integrations/hevy/    # cliente, esquemas, errores y almacenamiento raw
├── coach/                # contratos, agente PydanticAI y reglas de evidencia/aprobación
├── coaching/             # evaluación histórica, cálculos antropométricos y reglas con fuentes
├── mcp/                  # contratos públicos y herramientas MCP controladas para Hermes
├── metrics/              # cálculos deportivos deterministas
├── persistence/          # modelos y repositorios PostgreSQL
├── config.py             # configuración tipada desde .env/entorno
├── db.py                 # factoría SQLAlchemy (preparada para modelos futuros)
├── cli.py                # interfaz operativa de sincronización
└── main.py               # composición FastAPI
```

PostgreSQL es la fuente de verdad. El JSON crudo no sustituye la persistencia normalizada. El
cliente Hevy es async, inyectable y aislado; valida respuestas, traduce fallos HTTP/timeouts a
errores propios y pagina explícitamente. Crear o actualizar rutinas solo es accesible tras el flujo
auditado de propuesta, previsualización y confirmación final. En creación envía explícitamente
`folder_id: null` para la carpeta predeterminada y acepta la respuesta documentada bajo `routine`,
además de la forma directa observada en algunos endpoints/versiones. Los fallos de escritura exponen
solo un código seguro como `hevy_http_403`; nunca reproducen el cuerpo remoto. Consulta
`PROJECT_BRIEF.md`.

El estado operativo, el trabajo priorizado y las decisiones se mantienen en
`docs/PROJECT_STATE.md`, `docs/NEXT_STEPS.md` y `docs/DECISIONS.md`.
Las fórmulas, fuentes y límites del asesoramiento están en `docs/COACHING_KNOWLEDGE.md`.

## Sincronización y recuperación

`hevy sync` descarga primero una instantánea completa y solo entonces abre la transacción que la
aplica. Los registros se identifican por el ID estable de Hevy y un hash evita reescribir contenido
sin cambios. Una ausencia en una instantánea completa produce un borrado lógico trazado; si el
registro reaparece, se restaura. Cada ejecución queda en `sync_runs` con estado y contadores.

Si falla la descarga, no cambia ninguna entidad normalizada. Si falla la transacción, se revierte
completa y la ejecución queda marcada como fallida cuando PostgreSQL está disponible. Es seguro
repetir el comando. Antes de sincronizar en una instalación nueva ejecuta `uv run alembic upgrade
head`. Para revertir únicamente en desarrollo: `uv run alembic downgrade base` elimina todo el
esquema y sus datos.

## Métricas deportivas

El motor calcula bajo demanda desde PostgreSQL y no usa modelos de lenguaje. La API expone
`GET /metrics/summary` y `GET /metrics/exercises/{exercise_template_id}`. Las fórmulas, unidades,
dominios válidos y reglas de estancamiento están documentados en `docs/METRICS.md`.

## Entrenador IA

Hermes es el orquestador conversacional principal inicial. Arranca `gym-coach` por `stdio`, descubre
27 herramientas MCP y recibe contratos Pydantic independientes de Hevy y del ORM. Incluyen una
entrevista ampliada, evaluación histórica, mediciones/check-ins y el flujo controlado de aplicación
en Hevy. La instalación y configuración están en `docs/HERMES_SETUP.md`.

La integración PydanticAI existente se conserva como extra experimental para alternativas o
evaluaciones. Se instala con `uv sync --extra pydanticai`; admite Ollama local u OpenAI, pero no es
necesaria para FastAPI, sincronización, métricas, perfiles ni MCP.

Cada hallazgo y propuesta referencia evidencias internas. La CLI experimental `coach approve` solo
registra una decisión local. En MCP, aplicar exige además una previsualización ligada al hash exacto
y una confirmación final con token. No se conservan transcripciones ni respuestas brutas.

## MCP y Hermes

```bash
uv run gym-coach mcp --help
uv run gym-coach mcp
```

El segundo comando reserva stdout para el protocolo MCP. Hermes agrupa la entrevista y muestra un
resumen exacto con una confirmación por bloque persistido. Para rutinas, la petición explícita del
atleta aprueba el borrador; comparación y preview se muestran juntas y solo se pide una confirmación
final para la escritura exacta en Hevy.
Una respuesta de creación `2xx` no interpretable se contrasta con una instantánea remota; las
aplicaciones inciertas o parciales disponen de reconciliación explícita y nunca se reintentan enteras.

Las propuestas pueden declarar superseries mediante `superset_group`; los ejercicios consecutivos
con el mismo grupo se envían a Hevy con un `superset_id` compartido.

La skill puede enlazarse una sola vez al repositorio con
`./integrations/hermes/scripts/link-gym-coach-skill.sh --link`. Las modificaciones posteriores no
requieren otra copia; basta reiniciar el gateway para recargar la skill y el proceso MCP.

El onboarding usa primero el historial para no pedir un nivel autodeclarado cuando puede inferir la
profundidad de entrenamiento. Revisa objetivos, salud, mediciones, actividad, recuperación,
alimentación, limitaciones y preferencias. Los planes distinguen sesiones obligatorias y ubicación,
duración estimada y objetivos por repeticiones, tiempo o distancia. Cada cambio cita evidencias que
el backend vuelve a calcular o validar; las comparaciones de ejercicios, series y grupos musculares
se realizan de forma determinista en Python.

## Revisión automática post-entrenamiento

`uv run gym-coach automation poll-hevy` consulta el feed incremental público de Hevy. La primera
ejecución crea una línea base silenciosa; las siguientes sincronizan solo cuando existen eventos y
despiertan a Hermes una vez por entrenamiento nuevo mediante una cola PostgreSQL. El script de gate
para Hermes está en `integrations/hermes/scripts/gym-coach-workout-gate.sh`.

La tarea recomendada se ejecuta cada cinco minutos con la skill `gym-coach`, entrega las revisiones al
Topic `Revisiones` y mantiene los avisos operativos del gateway en `Alertas`; no invoca al modelo cuando no hay cambios. El gateway debe estar activo y
el usuario debe haber iniciado una conversación con el bot. Esta automatización sigue siendo de solo
lectura respecto a Hevy.
