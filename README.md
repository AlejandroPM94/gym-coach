# gym-coach

Base de un entrenador personal asistido por IA. Este primer hito ofrece una API de salud y
sincronización **solo lectura** con Hevy. Las métricas y el agente se incorporarán después.

## Requisitos e instalación

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker Compose (para PostgreSQL)
- Hevy Pro y una API key para los comandos reales de sincronización

```bash
uv sync
cp .env.example .env
# Edita .env localmente y define HEVY_API_KEY; no la pegues en logs ni en Git.
docker compose up -d postgres
```

La API key es opcional para arrancar la API y ejecutar tests; solo es obligatoria para Hevy.

## Ejecución

```bash
uv run uvicorn gym_coach.main:app --reload
curl http://127.0.0.1:8000/health

uv run gym-coach hevy check
uv run gym-coach hevy user
uv run gym-coach hevy routines
uv run gym-coach hevy workouts --limit 20
uv run gym-coach hevy exercise-templates
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
├── config.py             # configuración tipada desde .env/entorno
├── db.py                 # factoría SQLAlchemy (preparada para modelos futuros)
├── cli.py                # interfaz operativa de sincronización
└── main.py               # composición FastAPI
```

PostgreSQL será la fuente de verdad cuando se añadan los modelos. El JSON crudo no sustituye
la persistencia normalizada. El cliente Hevy es async, inyectable y aislado; valida respuestas,
traduce fallos HTTP/timeouts a errores propios y pagina explícitamente. No contiene operaciones
de escritura. Consulta la visión y fases en `PROJECT_BRIEF.md`.

El estado operativo, el trabajo priorizado y las decisiones se mantienen en
`docs/PROJECT_STATE.md`, `docs/NEXT_STEPS.md` y `docs/DECISIONS.md`.
