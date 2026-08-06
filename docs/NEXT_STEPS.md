# Siguientes pasos

Actualizado: 2026-08-06

## Siguiente hito

Validar el onboarding y la revisión de planificación en una conversación real de Hermes y preparar
Telegram como canal, manteniendo secretos fuera del repositorio y Hevy sin escritura.

## Tareas ordenadas

1. Actualizar la skill instalada y reiniciar Hermes para que descubra las 18 herramientas.
2. Ejecutar el onboarding real en terminal: preguntas progresivas, resumen, confirmación y lectura
   posterior del perfil y objetivos persistidos.
3. Pedir una revisión de varios meses usando métricas backend y comprobar que cada conclusión cita
   hechos o IDs de evidencia.
4. Solicitar un plan de prueba, revisar la comparación y confirmar una decisión local sin aplicar
   cambios en Hevy.
5. Configurar manualmente el canal Telegram de Hermes, guardando el token solo en su almacén local de
   secretos y repitiendo los casos anteriores desde el chat.
6. Crear casos de evaluación anonimizados para revisión, rutina nueva, mejora, datos insuficientes,
   rechazo de confirmación y limitación física.

## Dependencias

- Skill de Hermes instalada nuevamente desde la versión del repositorio.
- PostgreSQL saludable y sincronización Hevy reciente.
- Token de bot de Telegram creado por el usuario y configurado fuera del repositorio.

## Criterios de aceptación

- Hermes no guarda nada hasta mostrar el resumen y recibir confirmación explícita.
- Perfil y objetivos quedan versionados y pueden releerse en otra sesión/canal.
- Métricas se solicitan al backend y nunca se recalculan en Hermes.
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
