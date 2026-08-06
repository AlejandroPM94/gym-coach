# Siguientes pasos

Actualizado: 2026-08-06

## Siguiente hito

Completar el perfil y los objetivos estructurados para que Hermes pueda razonar sobre preferencias,
disponibilidad y metas reales mediante MCP, todavía sin escritura en Hevy.

## Tareas ordenadas

1. Completar el perfil del atleta y los objetivos versionados mediante la CLI existente.
2. Exponer objetivos y perfil completo por MCP con pruebas PostgreSQL específicas.
3. Añadir herramientas MCP de métricas deterministas ya calculadas, sin trasladar fórmulas a Hermes.
4. Probar manualmente Hermes con `openai-codex`, la skill preparada y datos reales sincronizados.
5. Definir un formato versionado de plan y previsualización; mantener toda aplicación real fuera de
   alcance hasta una aprobación adicional específica.
6. Crear casos de evaluación anonimizados para revisión, rutina nueva, mejora, datos insuficientes y
   limitación física.

## Dependencias

- Instalación y autenticación manual de Hermes, pendiente de aprobación del usuario.
- PostgreSQL saludable y una sincronización Hevy reciente.
- Revisión humana de los datos mínimos entregados a Hermes.

## Criterios de aceptación

- Perfil y objetivos completos, versionados y consultables mediante contratos MCP públicos.
- Métricas solicitadas al backend y nunca recalculadas por Hermes.
- Prueba manual de Hermes que consulta herramientas antes de afirmar hechos del historial.
- Ninguna llamada de escritura a Hevy.

## Trabajo aplazado

- Aplicación de propuestas en Hevy.
- RAG y base de conocimiento deportiva.
- Samsung Health, Health Connect, nutrición, Telegram e interfaz web.
- Almacenamiento opcional y comparación de fotografías, con consentimiento, cifrado, retención y
  borrado definidos antes de persistir cualquier imagen.
- Codex App-Server Runtime; el bucle normal de Hermes es el predeterminado inicial.
