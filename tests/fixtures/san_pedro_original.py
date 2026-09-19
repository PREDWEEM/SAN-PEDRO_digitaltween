"""Referencia independiente del motor San Pedro e1932343c42b29a666bb64de2eba903fe4bcf3b0.
Incluye parche SP-FINAL-2025-2026 y copias de sus funciones científicas.
"""
import numpy as np
import pandas as pd
UMBRAL_PRIMER_PICO = 0.20

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

def calculate_tt_scalar(t, t_base, t_opt, t_crit):
    if t <= t_base: return 0.0
    elif t <= t_opt: return t - t_base
    elif t < t_crit: return (t - t_base) * ((t_crit - t) / (t_crit - t_opt))
    else: return 0.0

def calcular_et0_hargreaves(jday, tmax, tmin, latitud=-33.7328):
    lat_rad = np.radians(latitud)
    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * jday)
    dec = 0.409 * np.sin(2 * np.pi / 365 * jday - 1.39)
    ws = np.arccos(-np.tan(lat_rad) * np.tan(dec))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(lat_rad) * np.sin(dec) + np.cos(lat_rad) * np.cos(dec) * np.sin(ws))
    ra_mm = ra / 2.45
    tmean = (tmax + tmin) / 2.0
    trange = np.maximum(tmax - tmin, 0)
    return np.maximum(0.0023 * ra_mm * (tmean + 17.8) * np.sqrt(trange), 0)

def balance_hidrico_superficial(
    prec,
    et0,
    w_max=15.0,
    ke_suelo=0.4,
    exponente_kr=0.0,
    devolver_kr=False,
):
    """Balance hídrico común con reducción Kr configurable.

    exponente_kr=0 conserva evaporación constante ET0 × Ke.
    exponente_kr=1 reproduce el secado dinámico usado en San Pedro/Tres Arroyos.
    """
    prec = np.asarray(prec, dtype=float)
    et0 = np.asarray(et0, dtype=float)
    n = len(prec)
    agua = np.zeros(n, dtype=float)
    kr_diario = np.ones(n, dtype=float)

    if n == 0:
        return (agua, kr_diario) if devolver_kr else agua
    if float(w_max) <= 0.0:
        raise ValueError("Wmax debe ser mayor que cero.")

    exponente = max(float(exponente_kr), 0.0)
    agua[0] = float(w_max) / 2.0
    for i in range(1, n):
        fraccion_agua = float(np.clip(agua[i - 1] / float(w_max), 0.0, 1.0))
        kr = 1.0 if exponente == 0.0 else fraccion_agua ** exponente
        kr_diario[i] = kr
        evaporacion_real = et0[i] * float(ke_suelo) * kr
        agua[i] = np.clip(
            agua[i - 1] + prec[i] - evaporacion_real,
            0.0,
            float(w_max),
        )

    return (agua, kr_diario) if devolver_kr else agua

def aplicar_filtro_primer_pico(df, umbral=UMBRAL_PRIMER_PICO):
    """
    Habilita la campaña desde el primer valor de EMERREL
    estrictamente superior al umbral. Los pulsos anteriores
    se guardan para auditoría y se cancelan en EMERREL.
    """
    df = df.copy()
    df["EMERREL_ANTES_FILTRO_PRIMER_PICO"] = df["EMERREL"].copy()

    candidatos = df.index[df["EMERREL"] > umbral].tolist()

    if candidatos:
        idx_primer_pico = candidatos[0]
        df["Primer_Pico_Habilitado"] = df.index >= idx_primer_pico
        df.loc[df.index < idx_primer_pico, "EMERREL"] = 0.0
    else:
        idx_primer_pico = None
        df["Primer_Pico_Habilitado"] = False
        df["EMERREL"] = 0.0

    return df, idx_primer_pico

class PracticalANNModel:
    def __init__(self, IW, bIW, LW, bLW):
        self.IW, self.bIW, self.LW, self.bLW = IW, bIW, LW, bLW
        self.input_min = np.array([1, 0, -7, 0])
        self.input_max = np.array([300, 41, 25.5, 84])
    def normalize(self, X): return 2 * (X - self.input_min) / (self.input_max - self.input_min) - 1
    def predict(self, Xreal):
        Xn = self.normalize(Xreal)
        a1 = np.tanh(Xn @ self.IW + self.bIW)
        emerrel = (np.tanh((a1 @ self.LW.T).flatten() + self.bLW) + 1) / 2
        return emerrel, np.cumsum(emerrel)

def parametros_superficie(cobertura_pct):
    """Deriva Ke y el modulador térmico desde cobertura físicamente reproducible."""
    cobertura = float(np.clip(cobertura_pct, 0.0, 100.0))
    puntos = [0.0, 30.0, 70.0, 100.0]
    ke_suelo = float(np.interp(cobertura, puntos, [0.85, 0.50, 0.25, 0.10]))
    modulador_termico = float(np.interp(cobertura, puntos, [0.95, 0.90, 0.85, 0.80]))
    return ke_suelo, modulador_termico

def simular_emergencia_local(
    df_meteo,
    modelo_ann,
    cobertura_pct,
    w_max,
    umbral_termoinhibicion=24.0,
    umbral_choque_hidrico=45.0,
    exponente_kr=0.0,
    latitud=-33.7328,
    latencia_jd=25,
    techo_choque=0.75,
    calentamiento_suelo=0.0,
    tau_decaimiento=None,
    beta_decaimiento=None,
    intensidad_decaimiento=None,
):
    """Motor biofísico único utilizado por la app y por el optimizador."""
    df = df_meteo.copy()
    df.columns = [str(c).upper().strip() for c in df.columns]
    df = df.rename(columns={
        "FECHA": "Fecha",
        "DATE": "Fecha",
        "DATETIME": "Fecha",
        "PREC": "Prec",
        "PRECIPITACION": "Prec",
        "PRECIPITACIÓN": "Prec",
        "LLUVIA": "Prec",
    })
    requeridas = ["Fecha", "TMAX", "TMIN", "Prec"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError("Faltan columnas meteorológicas: " + ", ".join(faltantes))

    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    for columna in ("TMAX", "TMIN", "Prec"):
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
    df = (
        df.dropna(subset=requeridas)
        .sort_values("Fecha")
        .drop_duplicates("Fecha", keep="last")
        .reset_index(drop=True)
    )
    if df.empty:
        raise ValueError("No hay datos meteorológicos válidos.")
    df["Prec"] = df["Prec"].clip(lower=0.0)
    df["Julian_days"] = df["Fecha"].dt.dayofyear

    ke_suelo, modulador_termico = parametros_superficie(cobertura_pct)
    df["Cobertura_Rastrojo"] = float(cobertura_pct)
    df["Ke_Suelo"] = ke_suelo
    df["Exponente_Kr"] = float(exponente_kr)

    df["Tmedia_aire"] = (df["TMAX"] + df["TMIN"]) / 2.0
    amplitud_termica = (df["TMAX"] - df["TMIN"]) / 2.0
    df["TMAX_suelo"] = df["Tmedia_aire"] + amplitud_termica * modulador_termico
    df["TMIN_suelo"] = df["Tmedia_aire"] - amplitud_termica * modulador_termico

    df["Tmedia"] = df["Tmedia_aire"]

    entradas_ann = df[["Julian_days", "TMAX", "TMIN", "Prec"]].to_numpy(float)
    emerrel_raw, _ = modelo_ann.predict(entradas_ann)
    df["EMERREL_RAW_ANN"] = np.clip(emerrel_raw, 0.0, 1.0)
    df["EMERREL_RAW"] = df["EMERREL_RAW_ANN"].copy()
    df["EMERREL"] = df["EMERREL_RAW_ANN"].copy()

    df["Prec_3d"] = df["Prec"].rolling(window=3, min_periods=1).sum()
    mascara_choque = (
        (df["Julian_days"] > int(latencia_jd))
        & (df["Julian_days"] <= 110)
        & (df["Prec_3d"] >= float(umbral_choque_hidrico))
    )
    df.loc[mascara_choque, "EMERREL"] = np.maximum(
        df.loc[mascara_choque, "EMERREL"],
        float(techo_choque),
    )
    df["Choque_Hidrico"] = mascara_choque

    df["ET0"] = calcular_et0_hargreaves(
        df["Julian_days"].values,
        df["TMAX"].values,
        df["TMIN"].values,
        latitud=float(latitud),
    )
    agua, kr_diario = balance_hidrico_superficial(
        df["Prec"].values,
        df["ET0"].values,
        w_max=float(w_max),
        ke_suelo=ke_suelo,
        exponente_kr=float(exponente_kr),
        devolver_kr=True,
    )
    df["W_superficial"] = agua
    df["Kr_Diario"] = kr_diario
    humedad_relativa = df["W_superficial"] / max(float(w_max), 1e-12)
    df["Humedad_Relativa"] = humedad_relativa
    df["Hydric_Factor"] = 1.0 / (1.0 + np.exp(-10.0 * (humedad_relativa - 0.30)))
    df["EMERREL"] *= df["Hydric_Factor"]
    df.loc[humedad_relativa < 0.20, "EMERREL"] = 0.0

    df["Lluvia_Recarga"] = (df["Prec"] >= float(w_max)).cummax()
    df.loc[~df["Lluvia_Recarga"], "EMERREL"] = 0.0

    df = aplicar_interaccion_termohidrica(
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
    )

    df["EMERAC"] = df["EMERREL"].cumsum()
    total_emergencia = float(df["EMERREL"].sum())
    df["EMERAC_NORMALIZADA"] = (
        df["EMERAC"] / total_emergencia if total_emergencia > 0.0 else 0.0
    )
    return df, idx_primer_pico, ke_suelo, modulador_termico
