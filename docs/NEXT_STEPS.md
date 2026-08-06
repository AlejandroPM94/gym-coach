# Siguientes pasos

Actualizado: 2026-08-06

## Siguiente hito

Validar el onboarding y la revisión de planificación en una conversación real de Hermes y preparar
Telegram como canal, manteniendo secretos fuera del repositorio y Hevy sin escritura.

## Tareas ordenadas

1. Actualizar la skill instalada a `0.3.0` y reiniciar Hermes; las 18 herramientas mantienen sus
   nombres, pero sus contratos de perfil y planes son más estrictos.
2. Reanudar el onboarding: Hermes debe preguntar por limitaciones/dolor, ejercicios problemáticos y
   preferencias, mostrar el perfil completo y guardar una nueva versión confirmada.
3. Pedir una revisión de varios meses usando métricas backend y comprobar que cada conclusión cita
   hechos o IDs de evidencia.
4. Mantener o rechazar el borrador antiguo sin aprobarlo; solicitar uno nuevo con justificaciones por
   cambio, sesión doméstica opcional y core prescrito por segundos.
5. Revisar el diff determinista y confirmar una decisión local sin aplicar cambios en Hevy.
6. Configurar manualmente el canal Telegram de Hermes, guardando el token solo en su almacén local de
   secretos y repitiendo los casos anteriores desde el chat.
7. Crear casos de evaluación anonimizados para revisión, rutina nueva, mejora, datos insuficientes,
   rechazo de confirmación y limitación física.

## Dependencias

- Skill de Hermes instalada nuevamente desde la versión del repositorio.
- PostgreSQL saludable y sincronización Hevy reciente.
- Token de bot de Telegram creado por el usuario y configurado fuera del repositorio.

## Criterios de aceptación

- Hermes no guarda nada hasta mostrar el resumen y recibir confirmación explícita.
- El onboarding diferencia «ninguna limitación» de «no preguntado».
- Perfil y objetivos quedan versionados y pueden releerse en otra sesión/canal.
- Métricas se solicitan al backend y nunca se recalculan en Hermes.
- Cada cambio del plan usa evidencia verificable y el backend calcula el diff.
- Telegram reproduce el flujo de terminal sin exponer el token ni datos en logs.
- Ninguna llamada de escritura a Hevy.

## Trabajo aplazado

- Aplicación de propuestas en Hevy.
- RAG y base de conocimiento deportiva.
- Samsung Health, Health Connect, nutrición, interfaz web y una integración Telegram propia dentro
  de `gym-coach`; el siguiente hito solo configura el canal ya proporcionado por Hermes.
- Almacenamiento opcional y comparación de fotografías, con consentimiento, cifrado, retención y
  borrado definidos antes de persistir cualquier imagen.
- Codex App-Server Runtime; el bucle normal de Hermes es el predeterminado inicial.
