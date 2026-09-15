# Siguientes pasos

Actualizado: 2026-09-15

## Google Drive activo

La cuenta de servicio, la lectura limitada a `gym-coach-health`, la primera importación real y el
timer systemd horario están activos. La revisión ampliada actual ya se importó con 30 días y
agregados de actividad, sueño, cardio y recuperación. Falta validar su presentación conversacional
mediante `get_weekly_coaching_review` y observar el siguiente ZIP diario.
El importador ya admite peso y composición BIA de openScale sync; falta verificar el primer pesaje
válido matutino después de retirar el registro de prueba.

## Siguiente hito

Prioridad: aceptación conversacional de la skill 0.9.0 y observación de datos nuevos reales.

1. En otras instalaciones, aplicar `c31e6c1124ab`, recargar Hermes y verificar las 41 herramientas;
   la instalación local ya está actualizada y comprobada.
2. Verificar las nuevas señales, `last_observed_at` y el primer pesaje openScale en la revisión
   semanal tras el siguiente backup.
3. Confirmar objetivos nutricionales con preview; validar etiqueta, receta y comida desde Telegram,
   cierre de día y corrección que invalida el cierre.
4. Ejecutar los escenarios conversacionales de `docs/COACHING_ACCEPTANCE.md`, incluido el nuevo
   informe post-entrenamiento, y registrar resultados
   sanitizados. La matriz preparada no equivale a una evaluación aprobada del modelo.
5. Preparar Oracle Cloud: red privada, volúmenes y copias de seguridad de PostgreSQL, secretos fuera
   de la imagen, servicios persistentes y migración verificada antes de cambiar las automatizaciones.

Validar una propuesta con superseries y la entrega automática post-entrenamiento en el Topic
`Revisiones`; después completar el resto del mapa de Topics y observar el primer reinicio con
avisos en `Alertas`.

Prioridad inmediata: recargar MCP, crear una propuesta nueva para la actualización pendiente y
verificar que una respuesta Hevy con `routine` como lista de un elemento se clasifica como aplicada.
No reutilizar la aplicación ni el token anteriores; si el resultado vuelve a ser incierto, usar la
reconciliación de la rutina fuente exacta.

La sincronización posterior a una escritura ya forma parte del flujo MCP. Debe validarse en una
aplicación real observando `sync_status=succeeded` y la rutina actualizada desde PostgreSQL.
También debe probarse `sync_hevy` desde Hermes cuando una sincronización posterior devuelva
`sync_status=failed`.

## Tareas ordenadas

1. Validar en Hermes una entrevista por bloques con una confirmación por bloque.
2. Generar y comparar una rutina con al menos una superserie.
3. Crear y mapear los Topics restantes de nutrición, objetivos y alertas.
4. Aplicar una rutina con superserie tras las confirmaciones requeridas y sincronizar Hevy.
5. Guardar un entrenamiento real y confirmar la revisión automática dentro de `Revisiones`.
6. Reiniciar el gateway sin trabajos activos y confirmar el aviso de arranque en `Alertas`.
7. Confirmar en un reinicio iniciado desde Telegram que `Gateway restarting` aparece tanto en el
   chat de origen como en `Alertas`.
8. Simular una caída durante un turno y verificar la continuación automática del último mensaje
   pendiente tras el siguiente arranque.

## Dependencias

- PostgreSQL saludable, migración nueva aplicada y sincronización Hevy reciente.
- Hermes gateway activo, MCP reiniciado y skill 0.9.0 enlazada al repositorio.
- Petición explícita del plan y una confirmación final distinta para aplicarlo.
- Capacidad suficiente en Hevy para las tres sesiones restantes.
- En otras instalaciones, la skill enlazada y el proceso MCP deben recargarse después del cambio.

## Criterios de aceptación

- La entrevista cubre objetivo, salud, mediciones voluntarias, actividad, recuperación y nutrición.
- El agente no pregunta nivel si el historial puede estimar profundidad y no afirma conocer técnica.
- Una meta de pérdida de grasa incluye alimentación, actividad, fuerza y seguimiento.
- Los cálculos básicos salen del backend y las recomendaciones importantes citan evidencia.
- Ninguna escritura Hevy ocurre sin una petición explícita, preview exacta y confirmación final;
  un timeout nunca crea un reintento.
- Un fallo remoto muestra un código seguro; una respuesta 2xx inválida queda bloqueada para
  reconciliación y nunca se reintenta como fallo limpio.
- La rutina sincronizada coincide con la previsualización aprobada y queda auditada.
- Toda escritura Hevy confirmada dispara una sincronización completa antes de devolver el resultado;
  si falla, se informa `sync_status=failed` y no se reintenta la escritura.
- La confirmación final se presenta como selección interactiva de aprobar/denegar en Telegram cuando
  Hermes dispone de botones; la respuesta textual sigue siendo solo fallback.
- `sync_hevy` exige confirmación local y devuelve contadores de la instantánea sin escribir en Hevy.
- Probar una rutina nueva con cargas prescritas en `weight_kg` y verificar que Hevy las muestra por
  serie tras la sincronización.
- Validar en una propuesta real que las cargas justificadas aparecen en Hevy y en la copia de
  PostgreSQL después de la sincronización posterior a la escritura.
- Una actualización cuya respuesta tenga `routine` como lista de un elemento se interpreta sin
  error; una lista de varios elementos se rechaza de forma segura.

## Trabajo aplazado

- Samsung Health: conservar más de 28 días en cada revisión o importar rutas GPS/muestras crudas.
- Integración con una app nutricional externa o catálogo externo automático.
- RAG/vector store; por ahora se usa catálogo versionado y trazable más investigación web.
- Interfaz web y una integración Telegram propia dentro de `gym-coach`.
- Diagnóstico médico, nutrición clínica y prescripción para patologías.
- Enrutamiento automático de modelos Hermes por complejidad; se mantiene fuera del backend hasta
  disponer de una política y pruebas de coste, latencia y calidad.
- Automatización del arranque de Docker Desktop en Windows: requiere activar la opción de inicio de
  Docker Desktop en la sesión del usuario; el repositorio solo controla la política de los servicios.
