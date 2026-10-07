# PREDWEEM Digital Twin · San Pedro

Gemelo digital de *Lolium multiflorum* basado en
[PREDWEEM/lolium_sanpedro2026](https://github.com/PREDWEEM/lolium_sanpedro2026).
Conserva la ANN y el motor **SP-FINAL-2025-2026**, e incorpora observaciones por
lote, cobertura variable y una capa adicional de calibración local 2026.

**PREDWEEM by Guillermo R. Chantre.** Copyright © 2026 Guillermo R. Chantre /
PREDWEEM. Todos los derechos reservados. Consulte [COPYRIGHT.md](COPYRIGHT.md).

## Ejecutar

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

En Streamlit Community Cloud, seleccione `PREDWEEM/SAN-PEDRO_digitaltween`,
rama `main` y archivo principal `app.py`.

## Visitas periódicas para reducir la hibernación

El workflow [mantener_activo.yml](.github/workflows/mantener_activo.yml) abre
la aplicación pública con Chromium cada cuatro horas (00:17, 04:17, 08:17,
12:17, 16:17 y 20:17 UTC). También admite ejecución manual desde
**Actions → Mantener activo el gemelo San Pedro → Run workflow** y se prueba
al modificar el workflow o su script.

La visita verifica el encabezado de San Pedro, el indicador de emergencia,
el panel principal y su gráfico, incluso dentro del iframe de Streamlit.
Si aparece el botón público para despertar la app, lo pulsa una vez y permite
hasta cinco minutos para iniciar. Una respuesta HTTP 200 por sí sola no cuenta
como éxito. Un error o la falta de carga deja la ejecución en estado fallido;
los avisos dependen de la configuración de notificaciones de GitHub Actions.
No requiere secretos ni modifica datos del lote. Playwright sólo se instala
en el ejecutor de Actions, no en la aplicación de Streamlit.

Esto reduce el riesgo de hibernación; **no garantiza disponibilidad continua**.
[Streamlit suspende las apps sin visitas durante 12 horas](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app#app-hibernation).
[GitHub puede demorar tareas programadas y desactivarlas tras 60 días sin actividad en un repositorio público](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
En ese caso, revise Actions y vuelva a habilitar el workflow. Para disponibilidad
permanente se requiere un alojamiento que no suspenda por inactividad.

## Funcionamiento

- **Configuración:** controles en el cuerpo, en tres columnas; sin panel lateral.
- **Estado:** dos gráficos a la par, flujo semanal (con opción diaria) y emergencia
  acumulada. Calendario del 1 de enero al 1 de octubre, pool histórico tenue y
  proyección del gemelo limitada a la meteorología disponible hasta siete días.
  Se conservan la curva base, calibración adicional y banda de 600–800 °Cd.
- **Calibración local 2026:** activada por defecto, con interruptor sobre el
  gráfico principal. La selección persiste durante la sesión y actualiza el
  estado, los escenarios y la exportación.
- **Observaciones:** carga y borrado de registros por lote. Acepta flujos con
  unidad PLM2 explícita, repeticiones con media por m² o emergencia acumulada.
- **Cobertura:** configuración efectiva original o serie FECHA + COBERTURA_PCT,
  también admitida en el archivo de emergencia. La serie diaria es una extensión
  exploratoria del gemelo; el motor original fue calibrado con cobertura constante.
- **Escenarios:** cambios exploratorios de lluvia y temperatura.
- **Trazabilidad:** procedencia, parámetros y descarga de la trayectoria diaria.

Los registros del lote se almacenan en `data/twin_state.db`, excluido de Git.
En alojamientos con disco efímero, conserve los archivos originales para
recuperar los datos después de un reinicio o redespliegue.

## Motor local conservado

San Pedro ya tiene una calibración fisiológica conjunta **2025–2026**. El gemelo
conserva sus parámetros exactos, documentados en
`sanpedro_calibration_2025_2026.json`:

| Parámetro | Valor |
|---|---:|
| Cobertura efectiva | 17,117654787448153 % |
| Wmax superficial | 21,835296520312887 mm |
| T0 termohídrico | 24,554776252844984 °C |
| Interacción hídrica α | 0,05239929751806027 °C |
| Pendiente logística térmica | 0,36599312676568485 °C |
| Ventana térmica | 7 días |
| Agotamiento de cohorte k | 0,4302565796601996 |
| Choque hídrico / Kr | 45 mm en 3 días / 0 |

La respuesta termohídrica es continua. `Termoinhibida` indica un factor menor
que 0,50 y sólo tiene función diagnóstica: no anula el flujo como un corte binario.
Tras la habilitación del primer pico mayor que 0,20, un reservorio causal reduce
la cohorte disponible según los pulsos ocurridos. Se conservan la latencia JD 25,
las coordenadas −33,7328, −59,7965, la ANN con temperaturas del aire y el reloj
triangular 2–20–30 °C. No se añade el techo de abril de otros sitios.

Los valores de cobertura de respaldo y Wmax permanecen congelados en la interfaz.
La cobertura observada permite explorar una trayectoria distinta cuando el usuario
la selecciona explícitamente.

## Referencias completas 2023–2026 y porcentaje acumulado

El pool histórico descriptivo tiene cuatro campañas de San Pedro, con la procedencia
disponible de cada una:

- **2023 y 2024** (incorporadas el 07/10/2026): conteos en **plantas/m²** de San
  Pedro (origen y unidades declarados por el usuario). 2023: 9 muestreos entre
  14/04 y 01/10; 2024: 15 muestreos entre 16/03 y 17/10. Se conservan el Excel
  recibido, los conteos en CSV y sus hashes en `data/reference/`. Se acumula y
  se interpola entre muestreos conservando la masa de cada intervalo.
  **Ninguna serie tiene un cero inicial**: la curva empieza en el primer conteo
  (2023: 17,5 % del total; 2024: 1,3 %), queda desconocida antes y no certifica
  ausencia previa de emergencia. El cierre se infiere de los ceros finales; el
  usuario no lo declaró expresamente. La meteorología recibida (sin estación
  informada, hasta 31/08/2023 y 30/09/2024) no se incorpora; sólo se registran sus hashes.
- **2025:** curva diaria ya procesada `emrel sp 2025 san pedro.xlsx`, guardada en
  el clasificador original. Se acumula su flujo y se divide por su suma. Aquí
  no están los conteos ni la meteorología originales de ese año.
- **2026:** 12 conteos entre 01/02 y 15/07 del adjunto. Se divide el acumulado
  observado por la suma registrada y se interpola el acumulado entre muestreos,
  conservando la masa de cada intervalo. La distribución diaria dentro del
  intervalo es desconocida. Antes del primer conteo la referencia queda vacía.

2025 y 2026 se aceptan como completas por la declaración del usuario del 20/09/2026.
No se agregan conteos posteriores al cierre; después de él se mantiene la referencia
acumulada en 1. Cada campaña tiene el mismo peso: la mediana de un día usa sólo las
campañas con dato esa fecha (`N_Campanas_Dia`). El mínimo y máximo describen los
años disponibles y **no son intervalos de confianza**. Sólo se muestran campañas
cuyo último conteo es anterior o igual al corte. Se conservan las exclusiones de 2010
y 2015. La alineación es por mes/día, con tratamiento explícito del 29 de febrero.

El pool admite **únicamente San Pedro 2023, 2024, 2025 y 2026**. Se verifica el
sitio y la procedencia de cada curva; otras campañas del manifiesto no se
incorporan automáticamente. Los archivos originales del clasificador se conservan,
pero sus otras curvas no participan del histórico mostrado ni del indicador semanal.

Los gráficos muestran una sola referencia **Pool histórico · orientativo**, sin
curvas individuales por año. Tanto el flujo como el acumulado provienen de ese
mismo pool, con una salvedad: el acumulado es la mediana de las campañas con dato
y el flujo es el **promedio de los flujos diarios de las campañas con dato en ambos
días consecutivos**. Así, una campaña sin cero inicial (2023, 2024) entra en su
primer conteo sin crear un salto en el pool; con 2025 y 2026 equivale a la derivada
de la mediana, pero con más campañas el flujo no suma 1 ni sigue a la mediana.
El máximo semanal histórico (indicador de intensidad) no cambia con 2023 y 2024:
la semana pico sigue siendo la de febrero (15/02; 19,2 % para el eje anual completo).
El detalle del rango, procedencia y descarga está bajo los gráficos y las
campañas utilizadas y excluidas se identifican en Trazabilidad.

2025 está disponible desde el 01/01/2026 y 2026 desde el 15/07/2026. Para una
consulta de 2027 se utilizan ambas. En cortes anteriores al 15/07/2026 sólo se
utiliza 2025; revisar 2026 con el motor ajustado a ese año sigue siendo retrospectivo.
La representación histórica en todo el calendario no extiende el pronóstico.

Ambos flujos se expresan en **porcentaje**, no en escalas 0–1 frente a 0–100:
el histórico respecto del total registrado de cada campaña y el gemelo respecto
del potencial modelado. No son densidades directamente comparables. La vista
semanal suma de lunes a domingo, conserva los totales y marca semanas parciales
en gris y con rayado; no inventa datos faltantes ni desagrega observaciones como conteos diarios.

### Alerta preventiva de inicio y fecha de monitoreo

Activada por defecto en **Configuración del gemelo**, con opción de desactivarla.
Consulta la trayectoria base de San Pedro desde el comienzo de la campaña y avisa
cuando `Primer_Pico_Habilitado` se activa entre mañana y el séptimo día, inclusive.
Muestra la fecha modelada y los días de anticipación disponibles para organizar
una recorrida. Funciona sin conteos de campo. Si hay un conteo positivo del lote
hasta el corte, informa que ya había emergencia a más tardar en esa visita;
no lo convierte en el día exacto de inicio.

El gráfico de flujo muestra una **flecha vertical violeta** sobre el día calendario
de la alerta inicial de monitoreo: **inicio modelado menos siete días**, con etiqueta
`DD/MM/AAAA · estimada`. Se conserva en las vistas semanal y diaria, sin moverla al
lunes ni al centro de la columna. Se recalcula con la información disponible al
corte; no acredita que se haya emitido un aviso en esa fecha. Sin inicio modelado
en el horizonte, con la alerta desactivada o fuera del calendario visible, no se dibuja.

La alerta **no desplaza curvas ni el origen del tiempo térmico** y conserva los
parámetros congelados, la interacción termohídrica y el reservorio causal de
San Pedro. Es un aviso visual en la app, no una notificación externa. Puede
anticipar hasta siete días; no garantiza detectar cada inicio. Si faltan días,
indica horizonte incompleto y no descarta emergencia; una señal positiva dentro
de los días disponibles sí activa vigilancia preventiva. Las revisiones con
meteorología histórica o emisiones posteriores al corte se identifican
explícitamente y no equivalen a pronósticos emitidos anticipadamente.
El detalle queda en Trazabilidad y en el estado guardado (`onset_alert`), incluida
la fecha estimada (`monitoring_alert_date`).

### Colores del flujo semanal

Las columnas completas se colorean con la misma clasificación del indicador:
**rojo** (>75 % del máximo semanal histórico), **naranja** (25–75 % inclusive),
**amarillo** (>0 y <25 %) y **verde** (flujo cero). El denominador proviene del
pool exclusivo de San Pedro disponible para la fecha consultada: 2025 y, desde
el 15/07/2026, también 2026. El color compara esas fracciones; la altura del
gemelo sigue expresando el porcentaje del potencial modelado del lote, y el
histórico el porcentaje de los totales registrados de las campañas.
El histórico usa los mismos colores con menor opacidad. Las semanas completas
sin flujo del gemelo se señalan con marcas verdes en y=0. Una semana parcial,
inválida o un flujo positivo sin máximo histórico disponible queda sin categoría,
en gris. El cursor muestra la categoría y el porcentaje del máximo.
Las barras abarcan lunes–domingo; el indicador a siete días usa mañana–día 7
y puede cruzar dos semanas calendario.

### Intensidad de emergencia y tiempo térmico

La intensidad compara la suma del flujo del gemelo de mañana a siete días después
con el **máximo de las semanas completas del pool histórico**, de lunes a domingo,
dentro del calendario visible hasta el 1 de octubre. El denominador es exactamente
el de las barras históricas del gráfico, con su escala porcentual y calendario.
No se usa el máximo de una sola campaña ni un incremento diario.

| Intensidad | Flujo previsto / máximo semanal histórico |
|---|---|
| 🔴 Alta | >75 % |
| 🟠 Media | 25–75 %, inclusive |
| 🟡 Baja | >0 y <25 % |
| 🟢 Nula | Flujo semanal exactamente cero |

Se necesitan siete fechas válidas, sin duplicados ni flujos negativos. Con datos
incompletos se muestra gris, sin atribuir intensidad baja o nula. Para un flujo
positivo también se requiere un pico histórico positivo. Es un índice relativo,
no una probabilidad ni una validación de precisión predictiva.

| TT desde el primer pico | Indicador |
|---|---|
| >800 °Cd | 🔴 FUERA DE CONTROL |
| >700 y ≤800 °Cd | 🟠 ULTIMO PLAZO |
| ≥600 y ≤700 °Cd | 🟡 CONTROL A TIEMPO |
| <600 °Cd | 🟢 AUN NO CONTROLAR |

El TT se evalúa en la fecha de consulta, sin redondear para asignar la categoría.

El porcentaje base ahora se calcula como:

```
progreso_base(t) = suma de flujos liberados hasta t / reservorio inicial (1)
remanente_base(t) = Reserva_Cohorte(t) - EMERREL(t)
progreso_base(t) + remanente_base(t) = 1
```

El reservorio existente utiliza lluvia, temperatura y estado hídrico para
liberar la cohorte. **Se elimina el anclaje al progreso histórico en la fecha
de consulta y la división por el total del archivo meteorológico disponible.**
Extender el horizonte o cambiar el pronóstico futuro no modifica el porcentaje
base de días anteriores, dentro de la precisión numérica. Una serie parcial
no se fuerza a terminar en 100 %. Cada campaña se ejecuta por separado.

El porcentaje representa la fracción del **potencial inicial modelado**. El
reservorio no es una medición del banco de semillas y puede conservar remanente
al cierre. Las referencias, por su parte, se expresan respecto del total
registrado de cada año: su comparación es descriptiva y no determina el
denominador del modelo. La capa adicional y la asimilación pueden corregir el
progreso Twin; `Reserva_Cohorte_Remanente` conserva el estado del motor base.
Los totales históricos no se transfieren como densidad a otros lotes.

Datos y procedencia: `data/reference/san_pedro_2023_2026{.json,_curves.csv}` y `data/reference/san_pedro_2023_2024_source.json`.
Para reproducir las referencias sin red:

```bash
python scripts/build_seasonal_reference.py
```

El interruptor controla **sólo la capa adicional del gemelo**. Al desactivarlo,
la curva base conserva su calibración fisiológica 2025–2026 y el pool histórico sigue activo.

## Meteorología

La serie `meteo_daily.csv` y el actualizador robusto conservan la jerarquía original:

1. **SIGA–INTA A872890:** observaciones prioritarias.
2. **ECMWF IFS histórico:** puente provisional para fechas vencidas sin una
   observación completa y válida, incluidos huecos interiores de la campaña.
3. **ECMWF IFS ENS 0,25°:** pronóstico operativo P50, conservando medias,
   percentiles, probabilidades de precipitación y cantidad de miembros.

La copia inicial tiene 268 días, del 01/01 al 25/09/2026: 248 observados,
13 provisionales y siete de pronóstico. La última observación SIGA es del
16/09; el estado histórico incluye los provisionales hasta el 18/09.
Los metadatos distinguen `Fuente`, `TipoDato`, `CalidadDato` y `Emision_UTC`.
Los datos provisionales se reemplazan cuando SIGA publica observaciones válidas.
La precipitación faltante nunca se transforma automáticamente en cero.

El workflow `actualizar_meteo.yml` actualiza a las 07:30 y 15:30 de Argentina y
admite ejecución manual. Conserva el cierre inclusivo del **01/10/2026**.
Después del cierre se completa el histórico sin consultar nuevos pronósticos.
La serie se valida antes de reemplazar el archivo operativo. Los nuevos
pronósticos se archivan en `data/historico_pronosticos/`; los archivos anteriores
siguen disponibles en el repositorio fuente.

El gemelo utiliza siete días desde el corte histórico. Un corte pasado usa la
meteorología actualmente archivada, no necesariamente la emisión disponible
entonces. Open-Meteo y la carga de un archivo son opciones adicionales.

## Calibración adicional 2026

Se incorporó `valida (1) (6).xlsx`, hoja `Hoja1`, columnas **fecha** y **plantas**.
La localidad se asigna por instrucción del usuario. El archivo no informa
superficie de muestreo, cobertura ni repeticiones. Se preservan los valores
originales, sin convertirlos a plantas/m² ni inferir repeticiones a partir
de los decimales.

| Dato | Valor |
|---|---|
| Fechas | 12, del 01/02 al 15/07/2026 |
| Intervalos de ajuste | 11, de 8 a 20 días |
| Suma registrada | 3.773,33 en la escala del adjunto |
| Primer intervalo | 01/02–21/02, 20 días, 2.213,33 plantas |
| Meteorología fija | 196 días, 01/01–15/07/2026 |
| Composición meteorológica | 193 observados SIGA y 3 provisionales ECMWF |
| Fechas provisionales | 09, 10 y 11 de junio |

El cero inicial delimita el primer intervalo. No se infiere ausencia de
emergencia antes del 01/02. Se conservan los intervalos irregulares, sin
convertirlos artificialmente en semanas.

La transformación `G(F) = logistic(offset + slope × logit(F))` utiliza
**offset 0,50 y slope 0,60**, reajustados después de revisar la normalización.
Conserva 0 y 1, la monotonía y los días sin flujo.
No modifica los pesos ANN, los parámetros fisiológicos ni el reloj térmico.
La escala auxiliar del ajuste no se transfiere como densidad del lote.

| Evaluación | RMSE base | RMSE con capa adicional |
|---|---:|---:|
| Ajuste retrospectivo, 11 intervalos | 347,65 | 205,42 |
| Evaluación retrospectiva por cortes, 5 intervalos | 17,1251 | 17,1289 |

RMSE en unidades del adjunto por intervalo. El ajuste mejora un **40,9 %**.
La evaluación por cortes presenta prácticamente el mismo RMSE (aumenta 0,02 %);
mejoran tres de los cinco intervalos, sin demostrar transferencia predictiva.
La pendiente alcanza el límite inferior permitido, 0,60. No se amplían sus
límites para mejorar artificialmente el ajuste. En cada corte se ajusta la capa adicional con los conteos previos y
se evalúa el intervalo siguiente usando meteorología realizada. **El motor base
ya fue calibrado con 2025 y 2026**, por lo que estos resultados no constituyen
validación independiente ni demuestran mejora predictiva. Se requieren nuevas
campañas y pronósticos con emisiones fechadas para evaluar esa transferencia.
Esta limitación aparece junto al gráfico principal y en la pestaña de calibración.

La capa se aplica a San Pedro desde el 15/07/2026, con el motor y referencia
compatibles. No se aplica a cortes anteriores porque incluiría observaciones
posteriores. Si se asimilan conteos 2026, se desactiva la capa adicional para
no reutilizar esos conteos también como ajuste del gemelo; la base conserva
su calibración previa. La incertidumbre no se reduce automáticamente.

Los conteos adjuntos se conservan como referencia y no se cargan en SQLite.
Para asimilarlos como densidad, primero debe confirmarse la superficie y
prepararse una columna PLM2. El importador no interpreta `plantas` como plantas/m².
La calibración de forma puede efectuarse sin esa conversión.

`data/calibration/` conserva el Excel, su CSV con los encabezados originales,
meteorología fija, perfil JSON, diagnósticos y procedencia con hashes.
Las actualizaciones meteorológicas no modifican esos datos congelados.
El código común recibe las cantidades mediante el campo interno
`Flujo_observado_PLM2`, usado aquí sólo como adaptador; los diagnósticos se
exportan con sufijo `Unidades` y no atribuyen densidad al adjunto.

Para reproducir el ajuste sin red:

```bash
python scripts/calibrate_site.py
```

## Verificación

```bash
python -m pytest -q
python -m compileall -q app.py predweem_twin scripts
```

Las pruebas verifican equivalencia de ANN, flujos y fisiología con el motor
original parcheado, la nueva normalización causal y conservación del reservorio,
reproducción de ambas referencias, termohidria continua, datos adjuntos y unidades,
perfil reproducible, asimilación, cobertura, meteorología y cierre de campaña.
GitHub Actions ejecuta las pruebas automáticamente. La procedencia científica
está documentada en [MODEL_PROVENANCE.md](MODEL_PROVENANCE.md).


## Disponibilidad operativa de porcentajes (01/10/2026)

**Disponibilidad de la normalización:** el motor SP-FINAL conserva el
reservorio inicial fijo (1) como denominador. El histórico San Pedro 2023–2026
es orientativo y no reemplaza esta escala. Extender el horizonte no modifica
el porcentaje pasado, salvo redondeo numérico. Se exportan los indicadores
`Normalizacion_Disponible` y `Normalizacion_Motivo`.

La asimilación, los gráficos y la persistencia distinguen porcentaje desconocido
de flujo cero. Si se recibe una trayectoria sin normalización válida, el estado
se muestra como “aún no estimable”, no como intensidad Nula. Los conteos originales
se conservan y se reutilizan al disponer de escala; las bases previas migran
sin perder registros. Estas protecciones no sustituyen el motor de reservorio.


## Actualización coherente de módulos en Streamlit

Una actualización en caliente podía mantener un constructor de estado antiguo
sin `normalization_available`, aunque la interfaz y los archivos ya estaban
actualizados. La aplicación ahora recarga sus módulos en orden de dependencia
cuando cambia la firma del código y renueva el modelo en caché con esa revisión.
Los cambios normales de fecha no recargan los módulos ni borran los conteos.
Se conserva la normalización causal de San Pedro como fracción del reservorio
inicial y su referencia local exclusiva de San Pedro 2023, 2024, 2025 y 2026.
