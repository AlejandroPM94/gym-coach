# Siguientes pasos

Actualizado: 2026-08-05

## Siguiente hito

Validación funcional del entrenador y continuidad conversacional segura, todavía sin escritura en
Hevy.

## Tareas ordenadas

1. Ejecutar una prueba real controlada tras configurar `OPENAI_API_KEY` localmente y revisar coste,
   latencia y calidad sin registrar el prompt.
2. Crear un pequeño conjunto de casos de evaluación anonimizados: revisión, rutina nueva, mejora,
   datos insuficientes y limitación física.
3. Añadir evaluadores deterministas para citas válidas, ajuste a días/minutos y ejercicios
   existentes cuando corresponda.
4. Modelar sesiones conversacionales guardando solo resúmenes explícitos y consentidos, no mensajes
   brutos ni IDs remotos de conversación.
5. Permitir consultar el detalle estructurado de una propuesta y compararlo con la rutina origen.
6. Definir un formato de plan aplicable y una previsualización de cambios; mantener la aplicación
   real fuera de alcance hasta una aprobación adicional específica.

## Dependencias

- `OPENAI_API_KEY` configurada únicamente en `.env` local.
- Revisión humana de las primeras respuestas reales y de los datos mínimos enviados.
- Decisión posterior sobre retención de resúmenes conversacionales.

## Criterios de aceptación

- Casos de evaluación repetibles y sin datos personales.
- Respuestas reales con evidencias existentes y sin métricas recalculadas.
- Coste y modelo observables sin exponer prompts ni secretos.
- Continuidad útil sin almacenar conversaciones completas.
- Ninguna llamada de escritura a Hevy.

## Trabajo aplazado

- Aplicación de propuestas en Hevy.
- RAG y base de conocimiento deportiva.
- Samsung Health, Health Connect, nutrición, Telegram e interfaz web.
