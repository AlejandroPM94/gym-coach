# Diario nutricional por Telegram

Hermes interpreta mensajes y etiquetas. PostgreSQL guarda el catálogo personal y el diario;
Python calcula raciones y totales con Decimal, sin llamadas a modelos.

## Uso

1. `search_nutrition_catalogue`: buscar productos o recetas habituales por nombre o código de barras.
2. `save_nutrition_food`: guardar datos confirmados por 100 g/ml, marca, estado crudo/cocinado/
   tal como se vende, ración de etiqueta opcional y procedencia. Para corregir una composición crear
   un ID nuevo.
3. `save_nutrition_recipe`: guardar ingredientes por ID y cantidades, número de raciones y,
   opcionalmente, peso cocinado total para servir gramos. También sirve para desayunos habituales.
4. `preview_nutrition_meal`: obtener el resumen calculado antes de confirmar una comida.
5. `log_nutrition_meal`: guardar tras una confirmación agrupada. Reutilizar el UUID `request_id`
   en reintentos; usar otro para una comida distinta.
6. `get_daily_nutrition`: consultar entradas y totales por fecha local (Europe/Madrid por defecto).
7. `void_nutrition_meal`: anular con motivo confirmado y registrar la sustituta. Conserva auditoría.

Ejemplos: «Guarda este yogur» con foto de etiqueta; «mi desayuno habitual contiene 200 g de ese
yogur y 40 g de avena»; «hoy he desayunado una ración de mi desayuno habitual»; «¿qué suma hoy?».

## Precisión

- Etiqueta o fuente consultada: indicar `source_reference`, sin enlaces privados ni secretos.
  Es procedencia confirmada, no certificación automática de la fuente por el backend.
- Foto de plato sin pesos: marcar `estimated_quantity`. Composición estimada: fuente `estimate`.
- No convertir g/ml ni peso crudo/cocinado sin datos. Para una unidad sin tamaño, pedir peso.
- Fibra desconocida es null, nunca cero. Se conserva la energía declarada por la fuente.
- Diario vacío o incompleto no demuestra ayuno, déficit ni falta de proteína. Totales solo de lo
  registrado; no se cambian objetivos automáticamente.
- No hay todavía búsqueda externa de alimentos ni escáner conectado a un proveedor. El barcode
  puede guardarse y buscarse como identificador exacto. Hermes puede consultar fuentes con sus herramientas, y leer
  etiquetas si su modelo admite imágenes. Si no puede leerlas, debe pedir datos legibles.
- El backend no almacena fotos ni incorpora OCR. No requiere otra API key.

## Arquitectura y activación

Migración `b62d8a04e391`: `nutrition_records` con tipo y fecha indexados, petición y resultado
tipados como JSON inmutable, confirmación y fecha de registro. Cada comida conserva su composición;
corregir un producto no modifica el historial. Instalación personal de un solo atleta.
La transacción evita duplicados por UUID y rechaza reutilizarlo con datos distintos.

Ejecutar `uv run alembic upgrade head` y `hermes gateway restart`. MCP expone 41 herramientas.
Las pruebas PostgreSQL usan bases temporales y cubren recetas, unidades, reintentos, correcciones
y fechas locales. El siguiente paso es una etiqueta y una comida reales en el Topic Nutrición.

## Objetivos y seguimiento (0.8.0)

Se añaden `preview_nutrition_target`, `save_confirmed_nutrition_target`,
`get_nutrition_day_review`, `confirm_nutrition_day` y `get_weekly_coaching_review`.

Los objetivos parten del perfil y objetivos confirmados y del último peso no nulo, no futuro y de
como máximo 30 días. Requieren revisiones de salud, nutrición y estilo de vida. Con solo año de
nacimiento, se exige una diferencia de 19–100 años para establecer conservadoramente mayoría de
edad. Las condiciones clínicas/medicación declaradas bloquean el cálculo automático general.

Python calcula mantenimiento estimado = Mifflin × factor de actividad; aplica el ajuste energético,
calcula proteína por kg, grasa como porcentaje de energía y carbohidratos restantes (4/4/9 kcal/g).
El factor de actividad (1,2–2,5), ajuste (-20 a +15 %), proteína (1,4–2 g/kg) y grasa (20–35 %) son
parámetros que deben justificarse y confirmarse, no valores que se seleccionen silenciosamente.
`adult_targets_v1` rechaza energía inferior a 1200 kcal o carbohidratos inferiores a 130 g: son límites
del alcance del producto, no garantía de adecuación individual ni tratamiento clínico. Los rangos
de proteína proceden de la regla ISSN existente; los de grasas/carbohidratos se apoyan en las
[referencias dietéticas de National Academies](https://www.nationalacademies.org/publications/10490).
La energía de la etiqueta se conserva. `adult_targets_v2` calcula también un objetivo de fibra con
un parámetro explícito y confirmable de 10–20 g por 1000 kcal (14 por defecto). Las versiones v1 ya
guardadas siguen siendo legibles y conservan fibra desconocida.

La preview contiene perfil, IDs de objetivos, medición, parámetros y huella; se vuelve a calcular
antes de guardar para rechazar modificaciones o datos obsoletos. Cada UUID identifica una versión
inmutable. No se permiten fechas iniciales pasadas. Para un día se selecciona la fecha vigente más
reciente y, a igual fecha, la última versión guardada. Los reintentos devuelven su versión original.

El cierre usa la huella del diario y la zona exactos; cambios posteriores de comidas invalidan el
cierre. Un reintento devuelve el acuse original sin volver a cerrar el diario modificado. Las
comparaciones (ingesta menos objetivo) se calculan solo para días completos con objetivo vigente.
La media semanal de ingesta informa cuántos días completos utiliza y no extrapola los ausentes.
Las diferencias semanales usan el objetivo vigente en cada día, incluso si cambió entre días.

La revisión recupera catorce días de mediciones y check-ins y 28 días de actividad para construir
una línea base personal. Compara medias de dos semanas: para peso
exige tres observaciones por semana; para cintura, una. Son reglas operativas transparentes, no una
inferencia de composición corporal. Incluye métricas deportivas y agregados Samsung Health cuando
están disponibles. No reajusta automáticamente objetivos ni rutinas.
