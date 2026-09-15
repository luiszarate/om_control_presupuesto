# Presupuesto Imago para Odoo 14 CE

Primera base funcional del control anual definido en `ESPECIFICACION_INICIAL.md`.

## Alcance implementado

- Presupuesto unico por compania y ejercicio, con flujo Borrador / Vigente / Cerrado.
- Catalogo editable de categorias y subcategorias (dos niveles).
- Partidas autorizadas o pendientes de definir.
- Regla unica Proyecto -> Categoria / Subcategoria por ejercicio.
- Tipos de cambio mensuales expresados como moneda de la compania por unidad.
- Motor unico por linea de OC: estados `purchase` y `done`, `price_total`, fecha de
  creacion de la OC y proyecto de cabecera aportado por `abs_project_po`.
- Deteccion opcional de `secihti_budget` y exclusion por `sec_project_id`.
- Resumen mensual nativo con diagnosticos de lineas sin tipo de cambio y compras
  sin clasificar.
- Dashboard Odoo 14 con filtros, tarjetas, comparativo por categoria y evolucion
  acumulada observada / referencia / proyectada.
- Exportacion XLSX privada con resumen, matriz mensual, compras, tipos usados y
  parametros e incidencias.
- Detalle temporal exacto del corte con apertura de la OC bajo permisos nativos.
- Fotografia de resumen y detalle al cerrar diciembre.
- Grupos de consulta, responsable y administrador, con reglas multiempresa.

## Instalacion de desarrollo

El nombre tecnico correcto es `om_control_presupuesto`. Esta carpeta de modulo se
encuentra dentro del directorio historico `om_control_prespuesto`; agregue como
`addons_path` el directorio que contiene directamente a `om_control_presupuesto`.

El modulo requiere `abs_project_po` y espera el campo almacenado
`purchase.order.project_id` hacia `project.project`. `secihti_budget` es opcional;
si esta instalado, el motor valida `purchase.order.sec_project_id` hacia
`sec.project` antes de considerar completo un reporte.

## Siguiente incremento

La siguiente fase completara el acceso desde cada celda mensual, la matriz de
tipos de cambio con doce columnas, el registro formal de motivos para cambios en
presupuestos vigentes y la conciliacion en una base Odoo 14 de pruebas.
