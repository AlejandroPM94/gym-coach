# Siguientes pasos

Actualizado: 2026-08-05

## Siguiente hito

Persistencia normalizada y sincronización idempotente de Hevy en PostgreSQL.

## Tareas ordenadas

1. Diseñar el modelo normalizado para usuarios, rutinas, entrenamientos, ejercicios y series.
2. Definir identidad externa, timestamps, borrados y reglas de idempotencia.
3. Crear la primera migración Alembic y tests de upgrade/downgrade.
4. Implementar repositorios y transacciones SQLAlchemy async.
5. Implementar sincronización incremental, reintentos y trazabilidad de ejecuciones.
6. Añadir pruebas de integración contra el PostgreSQL de Compose.
7. Documentar recuperación, reejecución y conservación de payloads raw.

## Dependencias

- PostgreSQL de Docker Compose operativo; el agente necesita acceso aprobado al socket Docker.
- Contratos Hevy observados y fixtures anonimizadas mantenidos.
- Decisión explícita sobre estrategia incremental: eventos de Hevy frente a paginación completa.

## Criterios de aceptación

- PostgreSQL es la única fuente de verdad normalizada.
- Dos sincronizaciones del mismo payload producen el mismo estado sin duplicados.
- Cambios y borrados quedan trazables.
- Ningún secreto o valor personal aparece en logs o errores.
- Migraciones y tests funcionan desde una base vacía.
- Format, lint, mypy y suite completa pasan.

## Trabajo aplazado

- Métricas deportivas y propuestas de progresión.
- PydanticAI, llamadas a modelos y RAG.
- Escritura o modificación de rutinas Hevy.
- Samsung Health, Health Connect, nutrición, Telegram e interfaz web.
