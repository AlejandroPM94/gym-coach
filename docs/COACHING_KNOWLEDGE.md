# Conocimiento de coaching

## Frontera

`gym-coach` calcula hechos personales en Python y entrega reglas generales con fuente, año, alcance
y limitaciones. Hermes interpreta esos resultados y puede consultar Internet, pero debe separar la
evidencia externa de los datos del atleta. Este catálogo no es RAG ni sustituye atención médica o
nutrición clínica.

## Cálculos deterministas

- Profundidad del historial: sesiones, días observados, semanas activas y ejercicios distintos. La
  etiqueta describe cantidad de evidencia, no técnica ni nivel de fuerza.
- IMC: peso dividido por altura al cuadrado; es un indicador de cribado, no composición corporal.
- Energía en reposo: Mifflin-St Jeor cuando existen peso, altura, edad y sexo necesario para la
  ecuación. No es por sí sola una prescripción calórica ni una medición de mantenimiento.
- Proteína: rango general de 1,4–2,0 g/kg/día para adultos sanos que entrenan. Se omite sin peso.

## Fuentes iniciales versionadas

- [ACSM 2026: entrenamiento de fuerza](https://acsm.org/resistance-training-guidelines-update-2026/)
- [OMS 2020: actividad física y sedentarismo](https://www.who.int/publications/i/item/9789240014886)
- [ISSN 2017: dietas y composición corporal](https://pubmed.ncbi.nlm.nih.gov/28630601/)
- [ISSN 2017: proteína y ejercicio](https://pmc.ncbi.nlm.nih.gov/articles/PMC5477153/)
- [AESAN: recomendaciones dietéticas para España](https://www.aesan.gob.es/AECOSAN/web/nutricion/subseccion/recomendaciones_dieteticas.htm)

## Reglas de uso

- Para pérdida de grasa, tratar déficit energético sostenible, fuerza, proteína, calidad dietética,
  actividad diaria, sueño y adherencia; nunca prometer reducción localizada.
- No fijar calorías exactas solo a partir de energía en reposo. Usar tendencias de peso y adherencia,
  y más adelante actividad de Samsung Health, para ajustar con incertidumbre explícita.
- No cambiar estructura por una sesión aislada. Usar varias exposiciones o una razón inmediata de
  seguridad/incompatibilidad.
- Investigar cuando el caso quede fuera del catálogo. Priorizar guías oficiales, consensos,
  revisiones sistemáticas y artículos primarios; registrar enlace y fecha en la respuesta.
- Derivar ante síntomas de alarma, trastorno alimentario, embarazo, enfermedad renal u otra situación
  que requiera diagnóstico, tratamiento o nutrición clínica.
