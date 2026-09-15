# Control de gasto y presupuesto — Imago Aerospace

**Versión:** 0.1 · 15 de septiembre de 2026  
**Destino:** Odoo 14 Community Edition  
**Estado:** propuesta para revisión; no se ha implementado el módulo.

## 1. Objetivo y alcance

Reproducir dentro de Odoo el control anual de la pestaña **Resumen**: presupuesto autorizado por categoría y subcategoría, compras acumuladas en MXN, saldo disponible, porcentaje restante, proyección lineal de cierre y distribución mensual. Cada importe deberá poder explicarse hasta la línea de compra que lo origina.

La primera versión incluirá dashboard, resumen mensual, presupuestos anuales, categorías configurables, asignación de proyectos, tipos de cambio mensuales y exportación XLSX.

Quedan fuera: Gastos Planeados, Personal nuevo como herramientas de planeación, nuevas contrataciones, flujos de caja, conciliación de pagos, gasto basado en facturas, bloqueo de compras por exceder presupuesto y reparto porcentual de una misma línea entre categorías. Sí se podrán capturar los importes anuales autorizados para nómina y personal: esto no implica desarrollar un planificador de personal.

## 2. Referencia revisada y hallazgos

Fuente: [Presupuesto 2026, pestaña Resumen](https://docs.google.com/spreadsheets/d/1gOLzUH_M6CMxxvFLel2ls5CfS0kV_XgVtsk9eI9om-w/edit?gid=0#gid=0). Se revisaron valores de A1:AD30 y fórmulas de C12:S22. No se modificó la hoja ni se utilizaron las pestañas de planeación.

La referencia contiene diez categorías, presupuesto de **$8,986,245.86** y gasto acumulado de **$1,101,691.52**. Los registros mensuales visibles corresponden a enero y febrero; no se deben interpretar como datos actualizados a septiembre.

| Categoría propuesta | Presupuesto de referencia MXN | Desglose autorizado identificado |
|---|---:|---|
| Manufactura Turix / Holom I+D | 750,000.00 | Importe directo |
| Pruebas de vuelo | 150,000.00 | Ground/Flight Tests |
| Nómina | 6,963,317.86 | Nómina actual: 4,225,092.75; personal ideal: 2,738,225.11 |
| Servicios de terceros | 86,700.00 | Medios de comunicación, social media manager, plan financiero, reclutamiento de gerente de ventas y servicios externos |
| Viajes | 200,000.00 | Importe directo |
| Infraestructura / Software / Equipo | 490,000.00 | Importe directo |
| Renta | 0.00 | Importe directo |
| Operación | 116,228.00 | Suscripciones: 26,760.00; servicios: 39,468.00; gastos de oficina: 50,000.00 |
| Otros gastos | 30,000.00 | Importe directo |
| Búsqueda de clientes | 200,000.00 | Importe directo |
| **Total** | **8,986,245.86** | |

En Servicios de terceros solamente Servicios Externos tiene un importe visible ($86,700); los otros conceptos están vacíos. En la carga inicial se distinguirá **pendiente de definir** de un cero expresamente autorizado. Los nombres anteriores normalizan la ortografía de la referencia y son editables.

Correcciones que incorporará el módulo:

- **Febrero:** I22 suma I13:I21 y omite I12 ($2,165.00). La suma correcta de las categorías es **$555,852.38**, frente a $553,687.38 en esa celda.
- **Proyección:** las categorías usan gasto / número de celdas no vacías × 12 / presupuesto. El total cuenta meses con fórmulas que devuelven cero y usa otra base temporal. Con un corte común a febrero, el cierre lineal sería **$6,610,149.12**, equivalente al **73.56%** del presupuesto total; no el 13.35% mostrado en G22.
- **Presupuesto cero:** Renta produce errores de división. Se mostrará “N/A”, con el motivo correspondiente.
- El encabezado “PROYECTADO FIN 25” se sustituirá por “Proyección al cierre 2026”, derivado del ejercicio elegido.

## 3. Reglas funcionales propuestas

### 3.1. Qué representa el gasto

**Confirmado por el usuario:** usar el **total con impuestos**. Se propone considerar órdenes confirmadas (`purchase`) y bloqueadas (`done`), excluyendo solicitudes de cotización, cotizaciones enviadas, pendientes de aprobación y canceladas.

El indicador se llamará **Gastado en OC**, con ayuda “Importe de compras confirmadas con impuestos; puede incluir compras todavía no pagadas”. El cálculo se realizará por línea, heredando el proyecto de cabecera, sin duplicar el total de la orden. Se excluirán secciones y notas. Se utilizará `price_total` en cada línea; subtotal e impuestos quedarán disponibles para conciliar contra la OC.

La fecha propuesta para asignar mes y año es la **fecha de confirmación**, convertida a la zona horaria configurada para el presupuesto, inicialmente America/Mexico_City. Una compra confirmada el 31 de diciembre y recibida en enero pertenece a diciembre. Una OC migrada sin fecha de confirmación aparecerá como incidencia; no se le asignará silenciosamente otra fecha.

Se toman las cantidades e importes vigentes de la OC, no las cantidades recibidas, facturadas o pagadas. Devoluciones y notas de crédito no reducen automáticamente este indicador si no cambian la OC. Los cambios y cancelaciones sí actualizan ejercicios abiertos. La versión inicial no reconstruye el estado histórico de una OC a una fecha pasada: “corte a febrero” selecciona compras por fecha, con su estado actual; el cierre anual conserva una fotografía verificable.

### 3.2. Proyectos y categorías

- Un catálogo por compañía con dos niveles: categoría y subcategoría opcional; orden de presentación y estado activo/archivado.
- En cada presupuesto anual se define qué proyectos contribuyen a cada categoría o subcategoría.
- Varios proyectos pueden contribuir al mismo destino. Un proyecto solamente puede tener un destino dentro del mismo ejercicio y compañía.
- **Confirmado por el usuario:** el proyecto se asigna en un campo de la cabecera de la OC. Todas las líneas heredan ese proyecto para este informe; no se utilizará la cuenta analítica de la línea como fuente alternativa.
- Verificado en `erp.imago.aero`: **`purchase.order.project_id`**, Many2one a **`project.project`**, almacenado y aportado por **`abs_project_po`**. Se reutilizará este campo y se declarará su dependencia. La v1 no introduce un nuevo flujo de reparto de compras.
- Una línea con proyecto sin regla o sin proyecto aparece en **Sin clasificar**. Su importe convertido sí forma parte del gasto total y reduce el disponible general; no se reparte artificialmente entre categorías.
- Un proyecto puede ir directamente a una categoría con subcategorías. En ese caso el detalle mostrará un renglón técnico “Sin subcategoría”, sin presupuesto adicional, para que los subtotales cuadren.
- Archivar una categoría impide nuevas selecciones, pero conserva su presupuesto e historial. Solo se elimina físicamente cuando no tiene referencias. Las reglas de un año no alteran las de otro.

### 3.3. Exclusión SECIHTI

| Situación | Tratamiento |
|---|---|
| `secihti_budget` no está instalado | No aplicar exclusión SECIHTI |
| Instalado y Proyecto SECIHTI vacío | La compra puede incluirse, sujeto a las demás reglas |
| Instalado y Proyecto SECIHTI asignado | Excluir la compra del gasto Imago |
| Instalado pero integración no reconocida | Mostrar error de integración; impedir presentar el reporte como completo |

La exclusión se evalúa **antes** de clasificar por proyectos internos. Un proyecto interno sin categoría no implica que sea SECIHTI. Verificado en la instalación: **`purchase.order.sec_project_id`**, Many2one a **`sec.project`**, en la cabecera. Cuando el módulo esté instalado, el criterio será **`('sec_project_id', '=', False)`**; una asignación excluye todas las líneas de la orden.

No se encontró el código de `secihti_budget` entre los módulos vecinos inspeccionados, pero se verificaron el nombre, tipo y ubicación del campo y su origen en **`secihti_budget`** mediante la interfaz técnica de Odoo. Resta revisar el código para definir el empaquetado de la integración opcional. No se usará el campo “Total MXN efectivo” de otro módulo como sustituto de la conversión mensual solicitada.

### 3.4. Monedas

Tabla por compañía, ejercicio, mes y moneda extranjera. Captura explícita: **1 USD = 17.23 MXN**. Valor mayor que cero; combinación única. MXN utiliza factor 1.

`importe_MXN = redondear_a_centavos(importe_de_línea × TC_del_mes_de_confirmación)`

Cada línea conservará para el informe su importe original, moneda, tipo de cambio aplicado y monto convertido. Los totales se sumarán desde esos importes de línea redondeados para garantizar conciliación con el detalle. Una eventual diferencia con convertir el total completo de la OC se identificará como redondeo por línea.

El tipo de cambio será una aproximación de gestión, independiente de los tipos contables de Odoo. La v1 propone captura manual mensual, como en la hoja; no descargará ni cambiará automáticamente tipos contables.

Si falta un tipo, mostrar **Reporte incompleto: N líneas sin convertir**, con moneda e importe original agrupados. El importe conocido podrá consultarse, pero gasto se identificará como parcial y disponible/proyección se mostrarán como “Pendientes de conversión” donde corresponda. No usar cero, factor 1 o el mes anterior como sustitución silenciosa. Exportar conservará esa advertencia y el listado pendiente.

### 3.5. Corte y fórmulas

El usuario elige ejercicio y **mes de corte**. Por defecto, último mes completo del ejercicio en curso; diciembre para años terminados. En enero, sin meses completos, se mostrará “Sin meses completos” hasta elegir enero como corte provisional. En ejercicios futuros no hay gasto ni proyección. Se permite elegir el mes actual con aviso “Mes en curso; proyección provisional”.

Para enero a un mes de corte `m` común a todas las categorías:

| Indicador | Fórmula |
|---|---|
| Presupuesto autorizado P | Suma de partidas autorizadas, sin duplicar padres e hijos |
| Gastado G | Suma de líneas elegibles convertidas, enero a m |
| Restante | P − G |
| Restante % | (P − G) / P × 100 |
| Proyección de gasto al cierre | G / m × 12 |
| Proyección de consumo % | (G / m × 12) / P × 100 |
| Desviación proyectada | Proyección de gasto − P; positiva indica exceso |

Los meses del periodo con cero gasto cuentan como transcurridos; los posteriores al corte se muestran como “—” y no entran en la proyección. Antes del primer mes, la proyección es N/A. Para P=0, los porcentajes son N/A; si G>0, se señala “Gasto sin presupuesto”. El saldo negativo se conserva y se identifica como excedido. El porcentaje total se calcula con los totales, nunca promediando porcentajes de categorías.

Semáforos propuestos: **Excedido** si G>P; **Riesgo al cierre** si G≤P y la proyección supera P; **Dentro del presupuesto** en los demás casos evaluables. “Sin presupuesto”, “Sin clasificar” e “Incompleto” tienen etiquetas propias. No se bloquean compras.

## 4. Pantallas y aspecto

Nueva aplicación **Presupuesto Imago**, integrada en el escritorio Odoo. Barra superior y controles coherentes con Odoo 14, tablas claras, números alineados a la derecha, moneda MXN visible y etiquetas además de colores. Configuración mediante formularios/listas nativos; dashboard y matriz mensual mediante una pantalla específica.

### A. Dashboard

- Filtros superiores: compañía, ejercicio, mes de corte y categoría.
- Tarjetas: autorizado, gastado en OC, disponible y proyección al cierre; porcentajes debajo.
- Gráfica horizontal por categoría: autorizado, gastado y proyección, en la misma escala.
- Evolución acumulada: gasto observado frente a referencia lineal del presupuesto; tramo proyectado diferenciado. La línea de presupuesto P/12 es solo una referencia de ritmo, no una autorización mensual.
- Categorías excedidas o con riesgo al cierre y acceso a compras sin clasificar/sin convertir.
- Cada barra abre su resumen o detalle aplicando los mismos filtros.

### B. Resumen mensual — equivalente principal de la hoja

Columnas: Categoría | Autorizado | Gastado | Restante | Restante % | Proyección MXN | Proyección % | Ene … Dic.

Categorías expandibles cuando exista desglose; fila total fija al final, encabezado y categoría fijos al desplazar la tabla horizontalmente. Un clic en un importe mensual abre las líneas de compra de esa categoría y mes; un clic en Gastado abre el acumulado. El modo compacto puede ocultar las dos columnas de proyección. Botones Actualizar y Exportar Excel.

### C. Presupuestos anuales

Lista: ejercicio, compañía, monto autorizado, estado y responsable. Formulario: cabecera con año/compañía/MXN y pestañas **Partidas**, **Proyectos**, **Tipos de cambio** e **Historial**.

Partidas muestra categoría, subcategoría, importe autorizado y nota. Cuando hay subcategorías, el total padre se calcula; cuando no las hay, se captura una partida directa. Nunca se suman simultáneamente un importe del padre y los mismos importes de sus hijos.

Flujo propuesto: **Borrador → Vigente → Cerrado**. Un presupuesto por compañía y año. Activación con responsable y fecha. Las modificaciones del vigente registran autor, fecha, motivo y valores anteriores. Duplicar al siguiente año copia estructura y reglas, permitiendo elegir si copiar importes; no copia gasto y deja tipos de cambio por revisar.

Cerrar guarda las reglas, tipos, partidas y líneas del informe para preservar el resultado; no bloquea Compras ni Contabilidad. Reabrir requiere responsable y motivo, conservando el cierre anterior. Los cambios posteriores de las OC no modifican una fotografía cerrada.

### D. Detalle de compras

Lista de consulta: OC, fecha de confirmación, proveedor, descripción de línea, proyecto, categoría/subcategoría, moneda, importe original, TC, importe MXN y estado de inclusión.

Filtros: categoría, proyecto, proveedor, moneda, mes, incluidas, sin clasificar, pendientes de conversión y excluidas por SECIHTI. Agrupación por categoría/proyecto/mes. Abrir OC conserva los permisos nativos de Compras. Desde una celda del resumen se abre exactamente el subconjunto que la suma.

### E. Configuración de categorías y proyectos

Lista editable de categorías con subcategorías, secuencia y activo. Reglas por ejercicio: **Proyecto → Categoría → Subcategoría opcional**. Mostrar cantidad de proyectos asociados y detectar duplicados antes de guardar.

Las categorías de la hoja son una propuesta de carga inicial, no una lista fija en código. La asignación exacta a proyectos reales se realizará después de leerlos en la instalación.

### F. Tipos de cambio mensuales

Matriz Moneda × Ene…Dic; cada celda expresa MXN por unidad. Indicar quién y cuándo modificó la tasa. Mostrar faltantes solo para monedas y meses con compras relevantes. Al cambiar una tasa de un ejercicio abierto, todos los informes usan el nuevo valor y se registra la modificación.

### G. Ajustes de integración

Compañía, zona horaria, política **total con impuestos**, campo de proyecto en cabecera verificado y estado de integración SECIHTI. Las políticas de importe/fecha se guardan también en el presupuesto anual para que un cambio global no altere años previos. No se añadirá un selector de base sin impuestos en esta versión. La configuración no permitirá introducir dominios o código arbitrario.

## 5. Exportación Excel

Un botón genera `.xlsx` con los filtros y el corte activos, utilizando el mismo resultado del dashboard:

1. **Resumen anual:** presupuesto, gasto, saldo, porcentajes y proyección por categoría.
2. **Detalle mensual:** matriz completa enero–diciembre, con subcategorías si se solicita.
3. **Compras:** líneas incluidas y trazabilidad a OC, proyecto y conversión.
4. **Tipos de cambio:** valores efectivamente usados.
5. **Parámetros e incidencias:** compañía, ejercicio, corte, impuestos, fecha de cálculo, criterio SECIHTI, sin clasificar/sin convertir y exclusiones autorizadas.

Importes y porcentajes serán celdas numéricas, con formatos y filtros, encabezados congelados y totales consistentes. Es una fotografía de valores calculados en Odoo; no depende de fórmulas externas. Se protegerá la escritura de textos de proveedores/OC para que no se interpreten como fórmulas de Excel. La exportación respetará los permisos y no creará adjuntos públicos.

## 6. Implementación técnica prevista

### Modelos

| Modelo propuesto | Responsabilidad |
|---|---|
| `imago.budget` | Ejercicio, compañía, estado, políticas, responsable y seguimiento |
| `imago.budget.category` | Catálogo jerárquico de dos niveles por compañía |
| `imago.budget.line` | Importe autorizado por destino en un ejercicio |
| `imago.budget.project.rule` | Proyecto y destino presupuestal por ejercicio |
| `imago.budget.exchange.rate` | MXN por unidad de moneda y mes |
| `imago.budget.snapshot` y líneas | Fotografía de cierre, versión y trazabilidad |
| Asistente de exportación | Filtros y descarga XLSX |

Nombre técnico sugerido del addon: `om_control_presupuesto` (corrección de la errata en el directorio actual `om_control_prespuesto`, a resolver antes de generar el addon).

Base CE: Compras, Proyectos, Web y seguimiento mediante Mail, más **`abs_project_po`**, verificado como proveedor del vínculo Compra → Proyecto en esta instalación. La compra estándar de Odoo 14 expone fecha de confirmación y subtotal/total; el cálculo reutilizará estos datos, junto con el proyecto de cabecera aportado por la extensión. [Código oficial de Compras, rama 14.0](https://github.com/odoo/odoo/blob/14.0/addons/purchase/models/purchase.py).

Un servicio Python construirá un conjunto único de líneas elegibles y devolverá totales, agrupaciones mensuales y diagnósticos. La matriz, gráficas y XLSX consumirán ese mismo servicio; las reglas monetarias no se duplicarán en JavaScript. Consulta acotada por compañía/año y lectura en lotes, sin consultas por cada celda. Actualizar vuelve a leer los datos vigentes; la interfaz mostrará la hora del cálculo y las exportaciones su propia hora de generación.

Frontend propuesto para esta versión: acción cliente con `web.AbstractAction`, plantillas QWeb y recursos incluidos localmente mediante herencia de `web.assets_backend`, compatibles con Odoo 14; gráficas sin dependencia de servicios externos ni de módulos Enterprise. Se validará contra los recursos de la instalación objetivo.

SECIHTI se resolverá mediante un adaptador con contrato explícito: estado de integración y criterio de exclusión. El addon principal no tendrá dependencia obligatoria de `secihti_budget`. La instalación/activación posterior del módulo SECIHTI deberá ser detectada; si el adaptador no es compatible, los informes afectados dejarán de marcarse como completos. Se podrá empaquetar un addon puente si el código real lo requiere.

### Permisos

- **Consulta de presupuesto:** ver dashboard, resumen y exportar dentro de compañías autorizadas.
- **Responsable de presupuesto:** capturar partidas, reglas y tasas; activar, ajustar, cerrar y reabrir con historial.
- **Administrador:** configuración de integración y accesos.

Reglas de compañía en todos los modelos. El resultado no usará privilegios elevados para evadir los permisos de compras. El acceso de consulta deberá ir acompañado de acceso de lectura a las compras de la compañía; si las reglas del usuario limitan compras, el informe se identificará como limitado a sus registros accesibles. Las fotografías y descargas deberán mantener un nivel de acceso equivalente al detalle que contienen.

## 7. Validación y aceptación

1. Instalar en Odoo 14 CE sin SECIHTI y consultar un ejercicio sin errores.
2. Con SECIHTI instalado, incluir asignación vacía y excluir asignada; comprobar integración añadida después de instalar el presupuesto.
3. Una OC MXN y una USD del mismo mes suman exactamente el detalle convertido. Ejemplo: 1,000 USD × 17.23 = 17,230 MXN.
4. RFQ y canceladas no contribuyen; confirmadas y bloqueadas sí. Cambios de importe/estado actualizan ejercicios abiertos.
5. Todas las líneas de una OC heredan el proyecto de cabecera sin duplicar importes; asociación duplicada de proyecto se rechaza.
6. Sin proyecto/regla aparece Sin clasificar y cuadra con el total; sin TC produce un informe incompleto, no un saldo engañoso.
7. Presupuesto cero, saldo negativo, mes sin compras, mes actual, año futuro y diciembre funcionan sin división entre cero.
8. Cada celda mensual coincide con su detalle; suma de categorías y Sin clasificar coincide con total. Porcentajes calculados sobre totales.
9. Con los importes de referencia y corte febrero, total $1,101,691.52, febrero $555,852.38 y proyección $6,610,149.12 / 73.56%.
10. Dashboard, resumen y XLSX coinciden para los mismos datos, filtros y momento de cálculo.
11. Cambio de año, permisos por compañía, archivo de categorías y cierre/reapertura preservan el historial.

Los datos de Sheets servirán para conciliar el resultado inicial; los gastos de la hoja no se importarán como compras adicionales. La fuente operativa será Odoo y cualquier diferencia se explicará por OC, fecha, impuestos, proyecto, exclusión o TC.

## 8. Orden de trabajo propuesto

1. **Acordar reglas y pantallas:** revisar esta especificación y el boceto.
2. **Verificar integración:** inspeccionar campos reales de proyecto y `secihti_budget`, estados, fechas e impuestos de una muestra de compras.
3. **Construir base y cálculo:** modelos, permisos, reglas anuales, tasas, pruebas de elegibilidad y conversión.
4. **Construir interfaz e informes:** dashboard, matriz, navegación a detalle y XLSX.
5. **Conciliar y entregar:** reproducir enero/febrero contra Odoo, explicar diferencias con Sheets y documentar instalación/uso.

### Decisiones pendientes para la siguiente revisión

- Revisar código de `abs_project_po` y `secihti_budget` para integración e instalación; sus campos de proyecto ya se identificaron en la interfaz técnica.
- Confirmar estados elegibles: la lista observada contiene registros de 2026 todavía en RFQ. Excluirlos puede impedir conciliar la hoja si esta ya los considera gastos.
- Confirmar fecha de confirmación como fecha de imputación y corte por mes.
- Confirmar qué conceptos en blanco de Servicios de terceros son cero autorizado y cuáles están pendientes.

## 9. Boceto de interfaz

El boceto navegable acompaña esta especificación y muestra Dashboard, Resumen mensual, Presupuesto anual, Proyectos y Tipos de cambio. Sus importes de resumen proceden de la referencia con las correcciones descritas y corte a febrero de 2026. Los nombres de proyectos de ejemplo no son asignaciones verificadas en Odoo. El boceto permite evaluar distribución, jerarquía y navegación; no es el módulo instalado ni una conexión a compras reales.

## 10. Inspección de Odoo realizada

Consulta de lectura en la sesión abierta de `erp.imago.aero`, compañía Imago Aerospace, el 15 de septiembre de 2026. Se inspeccionó la OC **P02242** y los metadatos de los campos de `purchase.order`; no se editaron órdenes ni configuración.

- Proyecto de cabecera: **Operaciones**, enlazado a `project.project`.
- Proyecto SECIHTI visible en cabecera y vacío en esta muestra.
- Total con impuestos: $64,910.16; subtotal $55,957.03; impuestos $8,953.13.
- Recepción: 30 de enero de 2026; confirmación: 4 de febrero de 2026. La selección de fecha cambia la columna mensual de esta compra.
- Se observaron registros RFQ y Purchase Order coexistiendo en la lista. Los estados y la fecha de imputación siguen como decisiones de negocio pendientes; no se infieren de la presencia del registro en Odoo.
