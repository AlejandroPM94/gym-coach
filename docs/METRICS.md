# Contrato de métricas deportivas

Actualizado: 2026-09-15

## Unidades y redondeo

- Carga: kilogramos (`kg`).
- Volumen externo: `kg·repeticiones`.
- e1RM: kilogramos, fórmula de Epley `peso × (1 + repeticiones / 30)`.
- Resultados decimales: dos posiciones, `ROUND_HALF_UP`.

## Series válidas

- Repeticiones totales: repeticiones positivas de series `normal`.
- Volumen: solo ejercicio `weight_reps`, serie `normal`, peso positivo y repeticiones positivas.
- e1RM: las mismas condiciones, limitado a 1-12 repeticiones.
- `warmup`, `drop`, tipos desconocidos, carga nula/cero, duración y distancia no producen volumen
  ni e1RM. Las repeticiones altas sí suman repeticiones y volumen, pero no e1RM.
- Peso corporal lastrado/asistido queda excluido del volumen `kg·repeticiones`; su progreso usa la
  carga externa o la asistencia y no necesita fingir una masa corporal ausente.

## Evolución

Se agrupa exclusivamente por `exercise_template_external_id`. Cada sesión informa series de trabajo,
repeticiones, volumen, mejor e1RM, cargas máxima/mínima, distancia, duración y RPE medio disponible.
La evolución selecciona una métrica según el tipo: e1RM, carga externa, asistencia (menos es mejor),
repeticiones, distancia o duración. Un primer registro establece línea base y no se marca como récord.
No se mezclan plantillas aunque compartan título o grupo muscular.
Los entrenamientos con borrado lógico se excluyen; una plantilla borrada se conserva para poder
interpretar correctamente entrenamientos históricos que todavía la referencian.

## Adherencia

`sesiones completadas / (objetivo semanal × días / 7)`, limitada al 100%. Se informa también cuántas
sesiones estaban vinculadas a una rutina. El objetivo se proporciona en cada consulta y todavía no
representa un plan persistido.

## Estancamiento

Regla por defecto: últimas 6 sesiones elegibles, al menos 4 sesiones, al menos 14 días entre primera
y última, y mejora de la métrica elegida inferior al 2%. Se admite e1RM, carga externa, menor
asistencia, repeticiones o distancia. La duración aislada queda como métrica de progreso descriptiva,
pero no produce una señal de estancamiento sin ritmo, carga u objetivo. Los resultados posibles son
`insufficient_sessions`, `insufficient_time_span`, `below_improvement_threshold` y `progressing`.
Es una señal determinista dependiente de la ventana, no un diagnóstico ni una recomendación.
