# Diseño de Telegram por Topics

## Recomendación

Usar un supergrupo privado con Topics activados, no un canal puro. Un canal sirve principalmente
para difusión; el supergrupo foro permite conversación bidireccional y separa cada tema con un
`message_thread_id`.

Topics iniciales recomendados:

- `Entrenamiento`: rutinas, progresiones y preguntas de sesiones.
- `Revisiones`: análisis automáticos después de cada entrenamiento.
- `Nutrición`: hábitos, adherencia y recomendaciones generales.
- `Objetivos y medidas`: objetivos, peso, perímetros y check-ins.
- `Alertas`: errores de sincronización y acciones pendientes.

## Frontera de responsabilidades

Telegram solo organiza la conversación. PostgreSQL sigue siendo la fuente de verdad para perfil,
objetivos, rutinas, entrenamientos, métricas, propuestas y aprobaciones. El `topic_id` no sustituye
ningún identificador de dominio.

## Trabajo pendiente

El supergrupo privado ya está creado, el bot está añadido y Hermes ha detectado los Topics
`Entrenamiento`, `Revisiones`, `Nutrición`, `Objetivos y medidas` y `Alertas`. El cron
post-entrenamiento entrega en `Revisiones` y el home channel de Hermes (avisos de arranque y
parada) apunta a `Alertas`. Los IDs privados no se guardan en el repositorio.

Para completar el mapa de áreas habrá que:

1. mantener el enrutamiento local mediante `chat_id` y `message_thread_id` sin subirlo a Git;
2. probar que una revisión automática llega a `Revisiones` y una propuesta a `Entrenamiento`;
3. confirmar el primer reinicio efectivo del gateway con el aviso en `Alertas`.

No se guardarán tokens, IDs privados ni configuración de `~/.hermes/` en este repositorio.
