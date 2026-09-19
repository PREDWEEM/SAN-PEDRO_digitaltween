# -*- coding: utf-8 -*-
"""Parametrización final San Pedro 2026 calibrada con campañas 2025-2026.

Este módulo mantiene fija la ANN original de PREDWEEM y reemplaza el corte
binario de termoinhibición por una respuesta continua temperatura × humedad,
seguida por un agotamiento causal de la cohorte germinable.

Los parámetros se congelan para la versión operativa San Pedro 2026.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# PARÁMETROS CONGELADOS — calibración conjunta 2025 + 2026
# ---------------------------------------------------------------------------
COBERTURA_FINAL = 17.117654787448153
WMAX_FINAL = 21.835296520312887
T0_TERMOHIDRICO_FINAL = 24.554776252844984
ALPHA_HIDRICA_FINAL = 0.05239929751806027
PENDIENTE_TERMOHIDRICA_FINAL = 0.36599312676568485
K_COHORTE_FINAL = 0.4302565796601996
VENTANA_TERMOHIDRICA_FINAL = 7
CHOQUE_HIDRICO_FINAL = 45.0
EXPONENTE_KR_FINAL = 0.0
ESCALA_LLUVIA_TH_FINAL = 45.0
CALIBRACION = "San Pedro 2025-2026"
VERSION_MOTOR = "SP-FINAL-2025-2026"


def aplicar_interaccion_termohidrica(
    df: pd.DataFrame,
    t0_base: float = T0_TERMOHIDRICO_FINAL,
    alivio_hidrico: float = ALPHA_HIDRICA_FINAL,
    pendiente_c: float = PENDIENTE_TERMOHIDRICA_FINAL,
    ventana_dias: int = VENTANA_TERMOHIDRICA_FINAL,
    escala_lluvia_mm: float = ESCALA_LLUVIA_TH_FINAL,
) -> pd.DataFrame:
    """Modula EMERREL con una respuesta térmica continua dependiente de humedad.

    H_int = HR * clip(Prec_3d / escala_lluvia, 0, 1)
    Tcrit_eff = T0 + alpha * H_int
    F_TH = 1 / (1 + exp((Tmedia_window - Tcrit_eff) / pendiente))

    La función no apaga abruptamente la emergencia: devuelve un factor entre 0
    y 1 y conserva columnas de auditoría para el reporte diario.
    """
    out = df.copy()
    requeridas = {"EMERREL", "Tmedia_aire", "Humedad_Relativa", "Prec_3d"}
    faltantes = requeridas.difference(out.columns)
    if faltantes:
        raise ValueError(
            "Faltan columnas para interacción termohídrica: "
            + ", ".join(sorted(faltantes))
        )

    ventana = max(1, int(ventana_dias))
    pendiente = max(float(pendiente_c), 1e-6)
    escala_lluvia = max(float(escala_lluvia_mm), 1e-6)

    out["Tmedia_TH"] = (
        out["Tmedia_aire"].rolling(window=ventana, min_periods=1).mean()
    )
    # Alias de compatibilidad con exportaciones previas.
    out["Tmedia_5d"] = out["Tmedia_TH"]

    hr = np.clip(
        pd.to_numeric(out["Humedad_Relativa"], errors="coerce").fillna(0.0),
        0.0,
        1.0,
    )
    wetting = np.clip(
        pd.to_numeric(out["Prec_3d"], errors="coerce").fillna(0.0) / escala_lluvia,
        0.0,
        1.0,
    )

    out["Indice_Hidrico_Termico"] = hr * wetting
    out["Tcrit_Efectiva"] = (
        float(t0_base) + float(alivio_hidrico) * out["Indice_Hidrico_Termico"]
    )

    z = (out["Tmedia_TH"] - out["Tcrit_Efectiva"]) / pendiente
    z = np.clip(z, -50.0, 50.0)
    out["Factor_TermoHidrico"] = 1.0 / (1.0 + np.exp(z))
    out["EMERREL_ANTES_TERMOHIDRIA"] = out["EMERREL"].copy()
    out["EMERREL"] = (
        out["EMERREL"] * out["Factor_TermoHidrico"]
    ).clip(0.0, 1.0)

    # Sólo diagnóstico. Ya no se utiliza para anular la emergencia.
    out["Termoinhibida"] = out["Factor_TermoHidrico"] < 0.50
    out["Termoinhibicion_Diagnostica"] = out["Termoinhibida"]
    return out


def aplicar_agotamiento_cohorte(
    df: pd.DataFrame,
    idx_primer_pico,
    k_cohorte: float = K_COHORTE_FINAL,
) -> pd.DataFrame:
    """Aplica un reservorio causal de cohorte germinable.

    f_t = 1 - exp(-k * EMERREL_potencial)
    Flujo_t = Reserva_t * f_t
    Reserva_(t+1) = Reserva_t - Flujo_t

    El mecanismo no usa información futura y reduce naturalmente la cola de
    emergencia cuando los pulsos tempranos consumen una fracción grande de la
    cohorte disponible.
    """
    out = df.copy()
    if "EMERREL" not in out.columns:
        raise ValueError("Falta columna EMERREL para agotamiento de cohorte.")

    out["EMERREL_ANTES_COHORTE"] = out["EMERREL"].copy()
    out["Reserva_Cohorte"] = 1.0
    out["Fraccion_Liberada_Cohorte"] = 0.0
    out["Factor_Cohorte"] = 1.0

    if idx_primer_pico is None:
        out["EMERREL"] = 0.0
        return out

    k = max(float(k_cohorte), 0.0)
    reserva = 1.0

    for i in out.index:
        if i < idx_primer_pico:
            out.at[i, "Reserva_Cohorte"] = 1.0
            out.at[i, "Factor_Cohorte"] = 0.0
            out.at[i, "EMERREL"] = 0.0
            continue

        potencial = float(np.clip(out.at[i, "EMERREL_ANTES_COHORTE"], 0.0, 1.0))
        out.at[i, "Reserva_Cohorte"] = reserva

        if potencial <= 0.0 or reserva <= 0.0:
            out.at[i, "Factor_Cohorte"] = 0.0 if potencial > 0.0 else 1.0
            out.at[i, "EMERREL"] = 0.0
            continue

        fraccion = 1.0 - np.exp(-k * potencial)
        flujo = reserva * fraccion

        out.at[i, "Fraccion_Liberada_Cohorte"] = fraccion
        out.at[i, "Factor_Cohorte"] = flujo / potencial if potencial > 0 else 0.0
        out.at[i, "EMERREL"] = flujo
        reserva = float(np.clip(reserva - flujo, 0.0, 1.0))

    out["EMERREL"] = out["EMERREL"].clip(0.0, 1.0)
    return out


def _reemplazar_unico(source: str, old: str, new: str, etiqueta: str) -> str:
    cantidad = source.count(old)
    if cantidad != 1:
        raise RuntimeError(
            f"Parche San Pedro no aplicado: '{etiqueta}' aparece {cantidad} veces; "
            "se esperaba exactamente una coincidencia."
        )
    return source.replace(old, new, 1)


def parchear_core_sanpedro(source: str) -> str:
    """Aplica de forma auditable la parametrización final al core conservado.

    El repositorio mantiene app_emergencia_core.py como base histórica. El
    launcher aplica este parche antes de compilarlo. Cada sustitución exige una
    única coincidencia para impedir que un cambio futuro del core deje el motor
    parcialmente actualizado sin aviso.
    """
    source = _reemplazar_unico(
        source,
        "# 🌾 PREDWEEM INTEGRAL vK4.9.15 VISUAL V3 — LOLIUM SAN PEDRO 2026",
        "# 🌾 PREDWEEM INTEGRAL vK4.9.20 SP FINAL — LOLIUM SAN PEDRO 2026",
        "versión",
    )
    source = _reemplazar_unico(
        source,
        "# - ESCUDO TERMOFISIOLÓGICO: Horizonte de termoinhibición dinámico ajustado a 5 días.",
        "# - TERMOHIDRIA CONTINUA: interacción temperatura × humedad calibrada 2025-2026 (ventana 7 días).\n# - AGOTAMIENTO DE COHORTE: reservorio causal calibrado 2025-2026 (k=0.43025658).",
        "cabecera termohidria",
    )
    source = _reemplazar_unico(
        source,
        'st.caption("San Pedro · configuración geográfica preliminar · parámetros ecofisiológicos pendientes de validación local")',
        'st.caption("San Pedro · parametrización local final calibrada con campañas completas 2025–2026 · motor termohídrico continuo + agotamiento de cohorte")',
        "caption principal",
    )

    cobertura_old = '''            cobertura_pct = st.slider(
                "Cobertura de Rastrojo en Suelo (%)",
                min_value=0, max_value=100, value=90, step=5,
                help="0% = Suelo desnudo / Labranza. 100% = Cobertura total (Ej. Cultivo de Servicio)."
            )'''
    cobertura_new = '''            cobertura_pct = st.number_input(
                "Cobertura efectiva calibrada (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(COBERTURA_FINAL),
                step=0.1,
                format="%.2f",
                disabled=True,
                help="Parámetro congelado por calibración conjunta San Pedro 2025–2026."
            )'''
    source = _reemplazar_unico(source, cobertura_old, cobertura_new, "cobertura")

    term_old = '''st.sidebar.markdown("**Ruptura de Dormición Estival (Escudo)**")
umbral_termoinhibicion = st.sidebar.number_input("Umbral Termoinhibición (°C)", 15.0, 35.0, 24.0, 0.5)'''
    term_new = '''st.sidebar.markdown("**Respuesta termohídrica continua — calibrada 2025–2026**")
umbral_termoinhibicion = float(T0_TERMOHIDRICO_FINAL)
st.sidebar.info(
    f"T0={T0_TERMOHIDRICO_FINAL:.2f} °C · ventana={VENTANA_TERMOHIDRICA_FINAL} d · "
    f"α hídrica={ALPHA_HIDRICA_FINAL:.3f} °C · pendiente={PENDIENTE_TERMOHIDRICA_FINAL:.3f} °C"
)'''
    source = _reemplazar_unico(source, term_old, term_new, "sidebar termohidria")

    choque_old = '''umbral_choque_hidrico = st.sidebar.slider(
    "Choque Hídrico 3 días (mm)",
    min_value=10.0,
    max_value=100.0,
    value=45.0,
    step=1.0
)'''
    choque_new = '''umbral_choque_hidrico = st.sidebar.number_input(
    "Choque Hídrico 3 días (mm)",
    min_value=10.0,
    max_value=100.0,
    value=float(CHOQUE_HIDRICO_FINAL),
    step=1.0,
    disabled=True,
    help="Valor congelado en la versión final San Pedro 2025–2026."
)'''
    source = _reemplazar_unico(source, choque_old, choque_new, "choque hídrico")

    source = _reemplazar_unico(
        source,
        'w_max_val = st.sidebar.number_input("Cap. de Campo Superficial (mm)", value=18.81, step=1.0)',
        'w_max_val = st.sidebar.number_input("Cap. superficial calibrada Wmax (mm)", value=float(WMAX_FINAL), step=0.1, format="%.2f", disabled=True)',
        "Wmax",
    )

    kr_old = '''exponente_kr = st.sidebar.slider(
    "Exponente Kr (secado superficial)",
    min_value=0.0,
    max_value=2.0,
    value=0.0,
    step=0.1,
    help=(
        "0 = evaporación ET0×Ke constante; 1 = reducción dinámica "
        "según el agua superficial disponible."
    ),
)'''
    kr_new = '''exponente_kr = st.sidebar.number_input(
    "Exponente Kr (secado superficial)",
    min_value=0.0,
    max_value=2.0,
    value=float(EXPONENTE_KR_FINAL),
    step=0.1,
    disabled=True,
    help="Kr=0 congelado por calibración conjunta San Pedro 2025–2026.",
)'''
    source = _reemplazar_unico(source, kr_old, kr_new, "Kr")

    source = _reemplazar_unico(
        source,
        '    if st.button("Ejecutar Barrido Hídrico"):',
        '    if st.button("Parámetros congelados — calibrador deshabilitado", disabled=True):',
        "calibrador 2D",
    )

    filtro_old = '''    df["Tmedia_5d"] = df["Tmedia_aire"].rolling(window=5, min_periods=1).mean()
    df["Termoinhibida"] = df["Tmedia_5d"] >= float(umbral_termoinhibicion)
    df.loc[df["Termoinhibida"], "EMERREL"] = 0.0
    df.loc[df["Julian_days"] <= int(latencia_jd), "EMERREL"] = 0.0
    df["EMERREL"] = np.clip(df["EMERREL"], 0.0, 1.0)

    df, idx_primer_pico = aplicar_filtro_primer_pico(df, umbral=UMBRAL_PRIMER_PICO)'''
    filtro_new = '''    df = aplicar_interaccion_termohidrica(
        df,
        t0_base=T0_TERMOHIDRICO_FINAL,
        alivio_hidrico=ALPHA_HIDRICA_FINAL,
        pendiente_c=PENDIENTE_TERMOHIDRICA_FINAL,
        ventana_dias=VENTANA_TERMOHIDRICA_FINAL,
        escala_lluvia_mm=ESCALA_LLUVIA_TH_FINAL,
    )
    df.loc[df["Julian_days"] <= int(latencia_jd), "EMERREL"] = 0.0
    df["EMERREL"] = np.clip(df["EMERREL"], 0.0, 1.0)

    df, idx_primer_pico = aplicar_filtro_primer_pico(df, umbral=UMBRAL_PRIMER_PICO)
    df = aplicar_agotamiento_cohorte(
        df,
        idx_primer_pico=idx_primer_pico,
        k_cohorte=K_COHORTE_FINAL,
    )'''
    source = _reemplazar_unico(source, filtro_old, filtro_new, "motor termohídrico + cohorte")

    return source
