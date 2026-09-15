# Project brief: gym-coach

## Visión

Construir un entrenador personal basado en IA que mantenga el plan, analice entrenamientos y
proponga progresiones explicables. La automatización debe ser auditable: cálculos deterministas,
interpretación separada y aprobación humana antes de modificar rutinas.

## Fases

1. **Base y Hevy read-only (completada):** FastAPI, CLI, cliente robusto,
   payloads raw y tests sin credenciales.
2. **Persistencia y sincronización (completada):** modelo normalizado, migraciones, instantáneas
   idempotentes y trazabilidad de sincronización.
3. **Motor deportivo (completada):** volumen, e1RM, tendencias, adherencia y estancamientos con
   tests de casos.
4. **Agente experimental (completada):** PydanticAI interpreta métricas y redacta propuestas
   justificadas; queda conservado como extra opcional y vía de evaluación.
5. **Hermes y MCP base (completada):** Hermes pasa a ser el orquestador principal y consulta
   contratos públicos estables del backend mediante un servidor local `stdio`.
6. **Onboarding y planes locales (completada):** perfil y objetivos confirmados/versionados,
   métricas deterministas y propuestas locales aprobables, sin escritura en Hevy.
7. **Contratos de planificación robustos (completada):** revisión explícita de seguridad,
   evidencias verificadas por cambio, prescripciones tipadas y diff determinista.
8. **Revisión automática post-entrenamiento (en validación):** eventos incrementales de Hevy,
   cola PostgreSQL y entrega mediante el cron de Hermes a Telegram.
9. **Coaching integral y aplicación Hevy (completada):** entrevista intensiva, nivel derivado del
   historial, mediciones/check-ins, reglas de entrenamiento/nutrición trazables y escritura de
   rutinas con doble confirmación.
10. **Seguimiento integral (completada):** diario y objetivos nutricionales, Samsung Health mediante
    Drive, composición openScale y revisión semanal con datos normalizados.
11. **Optimización del entrenador (completada, en aceptación real):** prescripción histórica,
    progresión por modalidad, recuperación contra línea base, estímulo muscular directo/indirecto e
    informe post-entrenamiento estructurado. Quedan pruebas conversacionales, no lógica determinista.

## Decisiones iniciales

Hito nutricional 2026-09-14: diario conversacional, catálogo personal con procedencia, recetas y
cálculo determinista de kcal/macros. PostgreSQL conserva versiones inmutables e historial de
correcciones. La documentación operativa está en `docs/NUTRITION.md`.

- Layout `src/` y composición por fronteras para impedir acoplar FastAPI al contrato de Hevy.
- Cliente HTTP async con HTTPX y dependencia inyectable para pruebas deterministas.
- Modelos Hevy estrictos en tipos conocidos pero con campos extra permitidos: la API pública se
  declara inestable y la tolerancia evita fallos por adiciones compatibles.
- Paginación 1-based. Tamaño 10 para rutinas/entrenamientos y 100 para plantillas, límites actuales
  del proveedor. El cliente corta por `page_count` y protege contra metadatos incoherentes.
- Captura raw por respuesta, con timestamp y UUID, fuera de Git. Puede contener información
  personal y no se considera backup ni fuente de verdad.
- La clave se mantiene como `SecretStr`, solo se usa al construir `api-key` y no aparece en repr,
  consola o logs.
- SQLAlchemy y Alembic gestionan el esquema normalizado, el perfil deportivo, los objetivos y las
  propuestas del entrenador.
- La respuesta verificada de `GET /v1/user/info` usa un sobre `data`, no `user`. Los diagnósticos
  de validación describen rutas y tipos, pero nunca reproducen valores recibidos.
- Hermes es el orquestador conversacional inicial y utiliza `gym-coach` mediante MCP `stdio`.
  PostgreSQL conserva la verdad estructurada y Hermes no sustituye métricas ni estado con memoria.
- PydanticAI queda como extra experimental. Hermes puede aplicar un plan en Hevy únicamente después
  de aprobación local, previsualización exacta, segunda confirmación y token de un solo uso.
- Hermes puede persistir perfil, objetivos y decisiones mediante herramientas MCP locales que
  exigen confirmación explícita. Las actualizaciones de perfil conservan instantáneas versionadas y
  las revisiones de objetivos archivan la versión sustituida.
- El backend distingue perfil no preguntado de una respuesta explícita sin limitaciones, verifica de
  nuevo toda evidencia al crear un borrador y calcula el diff de ejercicios, series y musculatura.
- El historial infiere profundidad y confianza, no competencia técnica. IMC, energía basal y rango
  de proteína se calculan en Python; las recomendaciones conservan fuente, año, alcance y límites.
- Hevy no publica webhooks en su API documentada: los entrenamientos nuevos se detectan por sondeo
  incremental con solapamiento, cursor persistente e idempotencia por ID externo.
