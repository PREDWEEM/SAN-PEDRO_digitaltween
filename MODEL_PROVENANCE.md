# Procedencia científica del gemelo de San Pedro

Fuente: [PREDWEEM/lolium_sanpedro2026](https://github.com/PREDWEEM/lolium_sanpedro2026/tree/e1932343c42b29a666bb64de2eba903fe4bcf3b0),
revisión `e1932343c42b29a666bb64de2eba903fe4bcf3b0`. El repositorio fuente no se modificó.

La interfaz, asimilación, persistencia y calibración externa se adaptaron del
[gemelo Azul](https://github.com/PREDWEEM/AZUL_digitaltween/tree/b40cbefd5e3bd0d0c184ec103c1fa61bceefb8c0).
Los pesos, la configuración fisiológica y la meteorología proceden de San Pedro.
La capa adicional se ajustó exclusivamente con el adjunto asignado a este sitio.

## Activos conservados

| Archivo | SHA-256 |
|---|---|
| `models/IW.npy` | `8614f90cd5f1337ae746690e474587b6fb22cf81652e694573cbfe4573f406d5` |
| `models/LW.npy` | `13cb012d7f4fe8e9e8399b31226e160ed60690cd4fb225a2de40375d250eb97b` |
| `models/bias_IW.npy` | `69423ba136a4caad97bed6b3aae2e7a387d87851a32eb5b2ab8de74dbcae3788` |
| `models/bias_out.npy` | `53451c25cc92da6bff25404a1e47815e38dfe58f7d83bb87c2d471298ec8a12d` |
| `models/modelo_clusters_k3.pkl` | `29f0508543bdda4b2520038c678a9df80ff9be555e0c15d5fa1f4da16a499d30` |
| `sanpedro_calibracion_final.py` | `5e21379a96cbba1d6ba8e5928dc775c72623d5bd56a83f5b8855141628e4fb89` |
| `sanpedro_calibration_2025_2026.json` | `e496a1de5b5f6e3e25c704a3d87d33b2d986d2e057522b364a17293418dd6492` |

## Correspondencia científica

La fuente ejecuta `app_emergencia_core.py` después de aplicar
`parchear_core_sanpedro` desde `sanpedro_calibracion_final.py`. El gemelo conserva
ese módulo sin cambios y utiliza sus funciones de interacción termohídrica y
reservorio de cohorte. No utiliza el core histórico sin parche como modelo final.

La referencia independiente `tests/fixtures/san_pedro_original.py` contiene
las funciones extraídas del core parcheado y copias de los auxiliares originales.
Las pruebas comparan ANN, ET0, agua superficial, factor hídrico, interacción
termohídrica, reservorio, flujo, acumulada y reloj térmico, con distintas
coberturas, capacidades hídricas y exponentes Kr.

- ANN de cuatro entradas: día juliano, TMAX, TMIN y precipitación del aire.
- Cobertura efectiva 17,117654787448153 %; Wmax 21,835296520312887 mm; Kr=0.
- Coordenadas −33,7328, −59,7965; ET0 conserva la latitud original.
- Latencia JD 25, recarga por lluvia diaria ≥ Wmax, corte HR < 0,20 y
  factor hídrico sigmoide con punto medio 0,30.
- Choque hídrico 45 mm en tres días hasta JD 110, piso 0,75 antes de filtros.
- Interacción continua temperatura × humedad con ventana 7 días y parámetros
  exactos del JSON congelado. Termoinhibida es sólo un diagnóstico.
- Primer pico > 0,20, seguido por el reservorio causal de cohorte con
  k=0,4302565796601996. No se incorpora el decaimiento del 15/04 de otros sitios.
- Reloj térmico triangular 2–20–30 °C; banda 600–800 °Cd.

La cobertura diaria, normalización parcial, asimilación y transformación externa
son extensiones del gemelo. La cobertura medida modifica el balance hídrico y
el diagnóstico de suelo, manteniendo las entradas neuronales originales.

## Referencia estacional y antecedentes del ajuste

El clasificador no se modifica. Se selecciona la campaña local
`emrel sp 2025 san pedro.xlsx` mediante el filtro `san pedro`, excluyendo 2010 y
2015. Una sola campaña no estima robustamente la variabilidad entre años.

El motor fuente ya fue calibrado conjuntamente con las campañas 2025 y 2026.
Los registros del adjunto entre el 21/02 y el 01/07 coinciden con los diez
registros de `valida (1).xlsx` del repositorio fuente; el nuevo adjunto añade
los ceros del 01/02 y 15/07. No constituyen un conjunto independiente del motor
base. La evaluación por cortes sólo diagnostica la capa adicional con el
motor previamente calibrado; no mide capacidad predictiva independiente.

## Meteorología, cantidades y trazabilidad

Los dos actualizadores, postprocesador P50, caché SIGA y serie operativa se
copian de la misma revisión fuente. El workflow conserva fuentes y horarios,
limita sus archivos versionados a meteorología y utiliza las dependencias
compatibles del gemelo. Se mantiene el cierre inclusivo del 01/10/2026.

La calibración usa 196 días fijos hasta el 15/07: 193 observaciones de SIGA
A872890 y tres provisionales ECMWF (9–11/06). No se emplean pronósticos futuros
para ajustar. Los provisionales están identificados en el CSV y en el JSON.

El adjunto `valida (1) (6).xlsx` contiene fecha + plantas, sin superficie ni
repeticiones. Se preserva la escala original. La localidad se asigna por
instrucción del usuario. No se infieren m² ni repeticiones de los valores
fraccionarios. Los diagnósticos se rotulan en unidades del adjunto.

Excel original, conteos, meteorología fija, hashes y revisión fuente quedan
registrados en `data/calibration/san_pedro_2026_source.json` y en el perfil JSON.
El fingerprint del modelo incluye pesos, core, referencia estacional, módulo
fisiológico y JSON de parámetros congelados. Las actualizaciones meteorológicas
diarias no modifican la copia utilizada en el ajuste.
