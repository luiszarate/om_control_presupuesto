# Presupuesto Imago para Odoo 14 CE

Primera base funcional del control anual definido en `ESPECIFICACION_INICIAL.md`.

## Alcance implementado

- Presupuesto unico por compania y ejercicio, con flujo Borrador / Vigente / Cerrado.
- Catalogo editable de categorias y subcategorias (dos niveles).
- Partidas autorizadas o pendientes de definir.
- Regla unica Proyecto -> Categoria / Subcategoria por ejercicio.
- Tipos de cambio mensuales expresados como moneda de la compania por unidad.
- Motor unico por linea de OC: estados `purchase` y `done`, `price_total`, fecha de
  recepcion (`date_planned`) y proyecto de cabecera aportado por `abs_project_po`.
- Deteccion opcional de `secihti_budget` y exclusion por `sec_project_id`.
- Resumen mensual nativo y persistente por usuario: el menu abre siempre el mismo
  resumen, recalculado con la ultima seleccion; cambiar presupuesto, mes de corte o
  categoria lo actualiza sin crear registros nuevos.
- Proyeccion lineal al cierre: gasto de enero al mes de corte / meses transcurridos x 12.
- Incidencias detalladas (OC sin fecha de recepcion, lineas sin tipo de cambio,
  integracion) que el responsable de presupuesto puede descartar o restaurar; las
  descartadas dejan de marcar el reporte como incompleto y quedan auditadas.
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

## Actualizacion del dashboard (14.0.1.1.1)

Corrige la clase CSS del contenedor de la accion y los atributos HTML que
deshabilitaban los filtros aun cuando habia un reporte. Incluye distribucion
adaptable, categorias accesibles con teclado, importes visibles y ejes de la
grafica en MXN. No modifica el motor de calculo ni los permisos.

Para aplicarlo en el servidor, copiar la carpeta `om_control_presupuesto` al
directorio de addons y actualizar el modulo en la base correspondiente
(`-u om_control_presupuesto`, usando la configuracion habitual de Odoo).
Reiniciar los procesos de Odoo y recargar el navegador sin cache para cargar
los nuevos recursos JS, SCSS y QWeb.

## Siguiente incremento

La siguiente fase completara el acceso desde cada celda mensual, la matriz de
tipos de cambio con doce columnas, el registro formal de motivos para cambios en
presupuestos vigentes y la conciliacion en una base Odoo 14 de pruebas.
