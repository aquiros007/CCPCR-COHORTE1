# Políticas de Caja Chica

Deje aquí el documento oficial de la política (PDF, Word o texto) y pídale a Claude:
"actualiza la configuración con la política".

Claude lo lee y:
1. Traslada los parámetros medibles a `config/politica.yaml` (límites, fondos, plazos, categorías,
   conceptos prohibidos, datos de la institución).
2. Liga cada regla automática con su artículo en `referencias_politica`, para que el informe diga qué
   norma se incumple.
3. Copia las cláusulas que requieren criterio a `reglas_cualitativas`; esas las revisa Claude al analizar
   cada liquidación.
