# gym-coach

Entrenador personal asistido por IA con sincronización Hevy de solo lectura, métricas
deterministas y propuestas estructuradas que requieren aprobación humana.

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
├── mcp/                  # contratos públicos y herramientas MCP controladas para Hermes
├── metrics/              # cálculos deportivos deterministas
├── persistence/          # modelos y repositorios PostgreSQL
├── config.py             # configuración tipada desde .env/entorno
├── db.py                 # factoría SQLAlchemy (preparada para modelos futuros)
├── cli.py                # interfaz operativa de sincronización
└── main.py               # composición FastAPI
```

PostgreSQL es la fuente de verdad. El JSON crudo no sustituye la persistencia normalizada. El
cliente Hevy es async, inyectable y aislado; valida respuestas,
traduce fallos HTTP/timeouts a errores propios y pagina explícitamente. No contiene operaciones
de escritura. Consulta la visión y fases en `PROJECT_BRIEF.md`.

El estado operativo, el trabajo priorizado y las decisiones se mantienen en
`docs/PROJECT_STATE.md`, `docs/NEXT_STEPS.md` y `docs/DECISIONS.md`.

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
18 herramientas MCP y recibe contratos Pydantic independientes de Hevy y del ORM. Trece son de
lectura; las cinco mutaciones solo guardan perfil, objetivos, borradores y decisiones locales bajo
confirmación o petición explícita. La instalación y configuración están en `docs/HERMES_SETUP.md`.

La integración PydanticAI existente se conserva como extra experimental para alternativas o
evaluaciones. Se instala con `uv sync --extra pydanticai`; admite Ollama local u OpenAI, pero no es
necesaria para FastAPI, sincronización, métricas, perfiles ni MCP.

Cada hallazgo y propuesta referencia evidencias internas. Las propuestas se guardan como
`draft`; `coach approve` y `coach reject` solo registran la decisión en PostgreSQL y nunca escriben
en Hevy. No se conservan prompts, conversaciones ni respuestas brutas del proveedor. Consulta el
contrato y las limitaciones en `docs/COACH.md`.

## MCP y Hermes

```bash
uv run gym-coach mcp --help
uv run gym-coach mcp
```

El segundo comando reserva stdout para el protocolo MCP. Hevy sigue siendo exclusivamente de
lectura. Antes de guardar un perfil, objetivo o decisión, Hermes debe mostrar el resumen exacto y
obtener confirmación explícita; aprobar una propuesta nunca la aplica en Hevy. Consulta los
contratos y el flujo manual en `docs/HERMES_SETUP.md`.

El onboarding obliga a revisar explícitamente molestias/limitaciones y preferencias, incluso cuando
la respuesta sea «ninguna». Los planes distinguen sesiones obligatorias y opcionales, ubicación,
duración estimada y objetivos por repeticiones, tiempo o distancia. Cada cambio cita evidencias que
el backend vuelve a calcular o validar; las comparaciones de ejercicios, series y grupos musculares
se realizan de forma determinista en Python.
