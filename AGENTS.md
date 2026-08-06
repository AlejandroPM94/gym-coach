# Instrucciones permanentes para agentes

## Alcance y arquitectura

- Mantén PostgreSQL como fuente de verdad; `data/raw/` es solo evidencia de depuración.
- Mantén proveedores externos detrás de `integrations/`; no propagues sus payloads por dominio.
- Implementa métricas deportivas deterministas en Python testeable. El LLM interpreta métricas,
  nunca calcula volumen, 1RM, adherencia, progresión o estancamientos básicos.
- Toda escritura o modificación de rutinas requiere aprobación explícita del usuario.
- Hermes es el orquestador conversacional inicial y accede al backend mediante MCP; no uses su
  memoria o skills como sustituto de PostgreSQL.
- Mantén PydanticAI como integración experimental y opcional; no añadas funcionalidad nueva sobre
  ella salvo que un hito lo solicite expresamente.
- No añadas RAG, Samsung Health, Health Connect, nutrición, Telegram o UI hasta que el hito
  correspondiente lo solicite.

## Ingeniería

- Usa Python 3.12+, tipado estricto, SQLAlchemy 2, Pydantic y APIs async donde haya I/O.
- Configura secretos solo mediante entorno/`.env`; nunca los registres, serialices o pruebes.
- Define errores de frontera explícitos y conserva la excepción original con `raise ... from`.
- Añade tests unitarios sin red para toda conducta nueva y tests de integración autocontenidos.
- Ejecuta antes de terminar: `ruff format .`, `ruff check .`, `mypy` y `pytest`.
- Usa migraciones Alembic para cualquier cambio de esquema; no alteres tablas manualmente.
- Mantén los contratos MCP públicos separados de modelos Hevy y ORM. Las escrituras locales de
  perfil, objetivos y decisiones requieren confirmación explícita y auditoría; ninguna herramienta
  puede escribir en Hevy hasta un hito específico con aprobación adicional.
- Documenta decisiones no obvias en `PROJECT_BRIEF.md` o como ADR cuando crezcan en alcance.
- Al terminar cada hito relevante, actualiza `docs/PROJECT_STATE.md`, `docs/NEXT_STEPS.md` y
  `docs/DECISIONS.md` para reflejar el estado verificado, el trabajo pendiente y las decisiones.
