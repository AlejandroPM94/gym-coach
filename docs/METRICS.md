# Contrato de métricas deportivas

Actualizado: 2026-08-05

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
- Peso corporal lastrado/asistido queda excluido hasta disponer de masa corporal fiable.

## Evolución

Se agrupa exclusivamente por `exercise_template_external_id`. Cada sesión informa repeticiones,
volumen y mejor e1RM; la evolución compara las dos últimas sesiones con e1RM elegible. No se mezclan
plantillas aunque compartan título o grupo muscular.
Los entrenamientos con borrado lógico se excluyen; una plantilla borrada se conserva para poder
interpretar correctamente entrenamientos históricos que todavía la referencian.

## Adherencia

`sesiones completadas / (objetivo semanal × días / 7)`, limitada al 100%. Se informa también cuántas
sesiones estaban vinculadas a una rutina. El objetivo se proporciona en cada consulta y todavía no
representa un plan persistido.

## Estancamiento

Regla por defecto: últimas 6 sesiones elegibles, al menos 4 sesiones, al menos 14 días entre primera
y última, y mejora del mejor e1RM inferior al 2%. Los resultados posibles son
`insufficient_sessions`, `insufficient_time_span`, `below_improvement_threshold` y `progressing`.
Es una señal determinista dependiente de la ventana, no un diagnóstico ni una recomendación.
