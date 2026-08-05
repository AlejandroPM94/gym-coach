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
4. **Agente (completada):** PydanticAI interpreta métricas y redacta propuestas justificadas;
   perfil, objetivos y decisiones se conservan sin escritura en Hevy.
5. **Canales y datos adicionales:** Samsung Health/Health Connect, nutrición y Telegram/app propia,
   cada integración desacoplada y con consentimiento explícito.

## Decisiones iniciales

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
- El agente usa OpenAI Responses mediante PydanticAI, salida estructurada estricta y evidencias
  deterministas. El modelo no dispone de herramientas de escritura y aprobar es una transición
  local, no una aplicación en Hevy.
