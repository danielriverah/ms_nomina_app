"""
Motor de cálculo de nómina - Mega Fresh Produce
Lógica verificada contra archivos NOMINA TOPES UMA 117.31
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Tuple

# ─────────────────────────────────────────────
# PARÁMETROS VIGENTES 2026
# ─────────────────────────────────────────────
UMA_DIA = 117.31
SM_DIA = 315.04          # Salario mínimo diario 2026
FACTOR_SDI = 1.0493      # Factor de integración base (se sobreescribe por trabajador)
DIAS_MES = 30.4          # Días promedio para proyección mensual

# ISR Mensual 2026 (SAT - Art. 96 LISR)
TABLA_ISR_MENSUAL = [
    (0.01,        746.04,         0.00,   0.0192),
    (746.05,      6_332.05,       14.32,  0.0640),
    (6_332.06,   11_128.01,      371.83,  0.1088),
    (11_128.02,  12_935.82,      893.63,  0.1600),
    (12_935.83,  15_487.71,    1_182.88,  0.1792),
    (15_487.72,  31_236.49,    1_640.18,  0.2136),
    (31_236.50,  49_233.00,    5_004.12,  0.2352),
    (49_233.01,  93_993.90,    9_236.89,  0.3000),
    (93_993.91, 125_325.20,   22_662.65,  0.3200),
    (125_325.21,375_975.61,   32_691.18,  0.3400),
    (375_975.62, 9_999_999.99,117_912.32, 0.3500),
]

# Subsidio al Empleo Mensual 2026 (tabla SAT)
TABLA_SUBSIDIO_MENSUAL = [
    (0.01,      1_768.96, 407.02),
    (1_768.97,  1_978.70, 406.83),
    (1_978.71,  2_653.38, 406.62),
    (2_653.39,  3_472.84, 392.77),
    (3_472.85,  3_537.87, 347.60),
    (3_537.88,  4_446.15, 347.60),
    (4_446.16,  4_717.18, 338.73),
    (4_717.19,  5_335.42, 269.23),
    (5_335.43,  6_224.67, 189.60),
    (6_224.68,  7_113.90, 189.60),
    (7_113.91,  7_382.33,  90.00),
    (7_382.34, 9_999_999.99, 0.00),
]

# Decreto Subsidio al Empleo (verificado contra SubEmpDecreto sheet)
DECRETO_SE = [
    (date(2024, 5, 1),  date(2024, 12, 31), 108.57, 248.93, 0.1182, 0.20, 390.12,  9_080.97),
    (date(2025, 1, 1),  date(2025, 1, 31),  108.57, 278.80, 0.1439, 0.20, 474.95, 10_170.62),
    (date(2025, 2, 1),  date(2025, 12, 31), 113.14, 278.80, 0.1380, 0.20, 474.64, 10_170.62),
    (date(2026, 1, 1),  date(2026, 1, 31),  113.14, 315.04, 0.1559, 0.20, 536.21, 11_492.66),
    (date(2026, 2, 1),  date(2026, 12, 31), 117.31, 315.04, 0.1502, 0.20, 535.65, 11_492.66),
]

# Topes de horas extras exentas (Art. 93 fracc. I LISR):
# 50% de 3 SM diarios x máx 5 días = exento máx (9 horas dobles fiscales máx)
HRS_EXTRA_MAX_FISCAL = 9  # horas dobles por semana para la parte fiscal
DIAS_HRS_EXTRA_MAX = 5    # máximo 5 días con horas extras

# Exento prima vacacional: 15 días de SM al año
PRIMA_VAC_EXENTA_DIAS_SM = 15

# Exento vacaciones: 15 días de SM
VAC_EXENTA_DIAS_SM = 15

# Aguinaldo exento: 30 días de SM
AGUINALDO_EXENTO_DIAS_SM = 30


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _buscar_tabla(valor: float, tabla: list) -> tuple:
    """Busca el renglón de una tabla progresiva."""
    for row in tabla:
        if row[0] <= valor <= row[1]:
            return row
    return tabla[-1]


def get_decreto_se(fecha_pago: date) -> float:
    """Retorna el monto mensual del Subsidio al Empleo por Decreto para la fecha dada."""
    for fi, ff, *_, se, _ in DECRETO_SE:
        if fi <= fecha_pago <= ff:
            return se
    return 535.65  # fallback 2026


# ─────────────────────────────────────────────
# IMSS - CUOTA OBRERO
# Verificado: 2.375% base + 0.4% excedente sobre 3*UMA
# ─────────────────────────────────────────────

def calc_cuota_obrera(sbc_dia: float, dias: int) -> float:
    """
    Cuota obrero IMSS semanal.
    Componentes (Art 106 LISS 2026):
      EyM excedente: 0.4% sobre SBC > 3*UMA/día
      EyM dinero:    0.25%
      IyV:           0.625%
      CyV:           1.125%
      Subtotal base: 2.0%
    + cuota adicional EyM proporcional = 0.375% sobre todo el SBC
    Total verificado = 2.375% + 0.4% max(0, SBC-3UMA)
    """
    excedente = max(0.0, sbc_dia - 3 * UMA_DIA)
    tasa_base = 0.02375
    tasa_exc  = 0.004
    return round((sbc_dia * tasa_base + excedente * tasa_exc) * dias, 2)


# ─────────────────────────────────────────────
# ISR - CÁLCULO MENSUALIZADO
# Método verificado: ISR2014(ingresos - exentos, dias) de VBA
# ─────────────────────────────────────────────

def _isr_mensual(base: float) -> float:
    """ISR causado mensual sobre una base gravable mensual."""
    if base <= 0:
        return 0.0
    li, ls, cf, tasa = _buscar_tabla(base, TABLA_ISR_MENSUAL)
    return cf + (base - li) * tasa


def _subsidio_mensual_sat(base: float) -> float:
    """Subsidio al empleo mensual tabla SAT (complementario al Decreto para salarios altos)."""
    if base <= 0:
        return 0.0
    for li, ls, sub in TABLA_SUBSIDIO_MENSUAL:
        if li <= base <= ls:
            return sub
    return 0.0


def calc_isr_semanal(
    ingresos_gravados_semana: float,
    dias: int,
    fecha_pago: date,
    exentos_semana: float = 0.0
) -> dict:
    """
    Calcula ISR semanal usando el método mensualizado del VBA.
    
    Args:
        ingresos_gravados_semana: suma de percepciones gravadas en la semana
        dias: días laborados en el período
        fecha_pago: para determinar SE por decreto
        exentos_semana: vacaciones exentas + prima vac exenta + hrs extras exentas
    
    Returns:
        dict con isr_calcula, sub_emp_acre, isr_neto, sub_emp_neto
    """
    base_semana = max(0.0, ingresos_gravados_semana - exentos_semana)
    
    # Proyectar a mensual: base / 7 * 30.4
    # (usamos días reales del período, mínimo 1 para evitar división por cero)
    dias_periodo = max(dias, 1)
    base_mensual = base_semana / 7 * DIAS_MES  # siempre sobre base de 7 días

    isr_m = _isr_mensual(base_mensual)

    # Subsidio: usamos el Decreto (verificado exacto) para salarios bajos
    # Para salarios altos (> límite decreto) el subsidio es 0
    se_decreto_mensual = get_decreto_se(fecha_pago)
    se_limite = next((lim for fi, ff, *_, se, lim in DECRETO_SE if fi <= fecha_pago <= ff), 11_492.66)

    if base_mensual <= se_limite:
        sub_mensual = se_decreto_mensual
    else:
        sub_mensual = 0.0

    # Prorratear al período (días reales)
    factor = dias / DIAS_MES
    isr_calc   = round(isr_m * factor, 2)
    sub_acre   = round(sub_mensual * factor, 2)
    isr_neto   = round(max(0.0, isr_calc - sub_acre), 2)
    sub_neto   = round(max(0.0, sub_acre - isr_calc), 2)  # cuando subsidio > ISR

    return {
        "isr_calcula":   isr_calc,
        "sub_emp_acre":  sub_acre,
        "isr_neto":      isr_neto,
        "sub_emp_neto":  sub_neto,
        "base_mensual":  round(base_mensual, 2),
    }


# ─────────────────────────────────────────────
# EXENTOS POR CONCEPTO (Art 93 LISR 2026)
# ─────────────────────────────────────────────

def exento_horas_extras(
    horas_dobles_fiscales: float,
    sd_fiscal: float
) -> Tuple[float, float]:
    """
    Calcula la parte exenta y gravada de horas extras.
    Exento: 50% del pago de HE, máximo 5*SM_dia por semana (9 hrs dobles max fiscal).
    Retorna (exento, gravado).
    """
    if horas_dobles_fiscales <= 0:
        return 0.0, 0.0
    # Pago por hora extra doble = SD / 8 hrs * 2
    costo_hr_extra_fiscal = sd_fiscal / 8 * 2
    total_he = round(horas_dobles_fiscales * costo_hr_extra_fiscal, 2)
    exento_50 = round(total_he * 0.50, 2)
    tope_exento = round(5 * SM_DIA, 2)  # máx exento semanal
    exento = min(exento_50, tope_exento)
    gravado = round(total_he - exento, 2)
    return exento, gravado


def exento_prima_vacacional(prima_total: float) -> Tuple[float, float]:
    """15 días de SM exentos de prima vacacional."""
    tope = round(PRIMA_VAC_EXENTA_DIAS_SM * SM_DIA, 2)
    exento = min(prima_total, tope)
    gravado = round(prima_total - exento, 2)
    return exento, gravado


def exento_vacaciones(vacaciones_total: float) -> Tuple[float, float]:
    """15 días de SM exentos de pago de vacaciones."""
    tope = round(VAC_EXENTA_DIAS_SM * SM_DIA, 2)
    exento = min(vacaciones_total, tope)
    gravado = round(vacaciones_total - exento, 2)
    return exento, gravado


# ─────────────────────────────────────────────
# CÁLCULO COMPLETO DE NÓMINA SEMANAL
# Separación fiscal (SBC) / no fiscal (diferencia real)
# ─────────────────────────────────────────────

def calcular_nomina_trabajador(
    # Datos del trabajador
    sbc_dia: float,          # Salario Base de Cotización diario (tope IMSS)
    sd_real_dia: float,      # Salario Diario Real (sin límite)
    factor_integracion: float,
    tipo_trabajador: str,    # 'PERMANENTE' o 'EVENTUAL'
    costo_hr_extra: float,   # valor fijo por hr extra (30, 35, 60...)
    credito_infonavit: float,

    # Incidencias de la semana
    dias_trabajados: int,    # días reales laborados (0-7)
    dias_incapacidad: int,
    tiene_bono: bool,        # 7° día / bono de asistencia
    horas_extras_reales: float,  # horas extras para pago REAL (valor fijo)
    horas_extras_fiscales: float,  # horas extras para cálculo ISR (máx 9 dobles)
    vacaciones_dias: int,
    prima_vacacional_dias: int,
    despensa: float,
    asistencia: float,
    puntualidad: float,
    compensacion: float,

    fecha_pago: date,
) -> dict:
    """
    Calcula la nómina semanal completa de un trabajador.
    Retorna parte fiscal (SBC), parte no fiscal (diferencia), y totales.
    """
    dias_netos = dias_trabajados - dias_incapacidad

    # ── SD fiscal (basado en SBC) ──────────────────────
    sd_fiscal = round(sbc_dia / factor_integracion, 6)

    # ── Bono (7° día): se paga solo si trabajó todos los días asignados ──
    # Para permanentes: bono = 1 día de SD real
    bono_real = round(sd_real_dia, 2) if tiene_bono else 0.0
    bono_fiscal = round(sd_fiscal, 2) if tiene_bono else 0.0

    # ── PERCEPECIONES REAL (para neto a pagar) ─────────
    sueldo_real     = round(sd_real_dia * dias_netos, 2)
    vacaciones_real = round(sd_real_dia * vacaciones_dias, 2) if vacaciones_dias else 0.0
    prima_vac_real  = round(vacaciones_real * 0.25, 2) if prima_vacacional_dias else 0.0
    hrs_extra_real  = round(horas_extras_reales * costo_hr_extra, 2)

    suma_real = (
        sueldo_real + bono_real + hrs_extra_real
        + vacaciones_real + prima_vac_real
        + despensa + asistencia + puntualidad + compensacion
    )

    # ── PERCEPECIONES FISCAL (basado en SBC) ───────────
    sueldo_fiscal     = round(sd_fiscal * dias_netos, 2)
    vacaciones_fiscal = round(sd_fiscal * vacaciones_dias, 2) if vacaciones_dias else 0.0
    prima_vac_fiscal  = round(vacaciones_fiscal * 0.25, 2) if prima_vacacional_dias else 0.0

    # Horas extras fiscales: max 9 horas dobles, costo = SD/8*2
    exento_he, gravado_he = exento_horas_extras(horas_extras_fiscales, sd_fiscal)
    total_he_fiscal = round(exento_he + gravado_he, 2)

    exento_pv, gravado_pv = exento_prima_vacacional(prima_vac_fiscal)
    exento_vac, gravado_vac = exento_vacaciones(vacaciones_fiscal)

    # Exentos totales para ISR
    exentos_isr = round(exento_he + exento_pv + exento_vac, 2)

    suma_fiscal = (
        sueldo_fiscal + bono_fiscal + total_he_fiscal
        + vacaciones_fiscal + prima_vac_fiscal
        + despensa + asistencia + puntualidad + compensacion
    )

    # ── DEDUCCIONES FISCAL ─────────────────────────────
    cuota_obrera = calc_cuota_obrera(sbc_dia, dias_netos + (1 if tiene_bono else 0))
    
    dias_isr = dias_netos + (1 if tiene_bono else 0)
    isr = calc_isr_semanal(suma_fiscal, dias_isr, fecha_pago, exentos_isr)
    
    infonavit = round(credito_infonavit, 2) if credito_infonavit else 0.0

    suma_deduc_fiscal = round(cuota_obrera + isr["isr_neto"] + infonavit, 2)

    # ── NETO FISCAL ────────────────────────────────────
    neto_fiscal = round(suma_fiscal - suma_deduc_fiscal, 2)

    # ── DIFERENCIA (no fiscal) ─────────────────────────
    # Diferencia = neto real - neto fiscal (se paga en efectivo)
    deducciones_real_estimadas = suma_deduc_fiscal  # mismas deducciones base
    neto_real = round(suma_real - deducciones_real_estimadas, 2)
    diferencia = round(neto_real - neto_fiscal, 2)

    return {
        # Identificación
        "dias_trabajados":    dias_trabajados,
        "dias_incapacidad":   dias_incapacidad,
        "dias_netos":         dias_netos,
        "tiene_bono":         tiene_bono,

        # Real (pago total)
        "sueldo_real":        sueldo_real,
        "bono_real":          bono_real,
        "hrs_extra_real":     hrs_extra_real,
        "vacaciones_real":    vacaciones_real,
        "prima_vac_real":     prima_vac_real,
        "suma_real":          suma_real,

        # Fiscal (lo que se timbra)
        "sd_fiscal":          sd_fiscal,
        "sueldo_fiscal":      sueldo_fiscal,
        "bono_fiscal":        bono_fiscal,
        "total_he_fiscal":    total_he_fiscal,
        "exento_he":          exento_he,
        "gravado_he":         gravado_he,
        "vacaciones_fiscal":  vacaciones_fiscal,
        "exento_vac":         exento_vac,
        "gravado_vac":        gravado_vac,
        "prima_vac_fiscal":   prima_vac_fiscal,
        "exento_prima_vac":   exento_pv,
        "gravado_prima_vac":  gravado_pv,
        "despensa":           despensa,
        "asistencia":         asistencia,
        "puntualidad":        puntualidad,
        "compensacion":       compensacion,
        "suma_fiscal":        suma_fiscal,
        "exentos_isr":        exentos_isr,

        # Deducciones
        "cuota_obrera":       cuota_obrera,
        "isr_calcula":        isr["isr_calcula"],
        "sub_emp_acre":       isr["sub_emp_acre"],
        "isr_neto":           isr["isr_neto"],
        "sub_emp_neto":       isr["sub_emp_neto"],
        "infonavit":          infonavit,
        "suma_deduc":         suma_deduc_fiscal,

        # Netos y diferencia
        "neto_fiscal":        neto_fiscal,
        "neto_real":          neto_real,
        "diferencia":         max(0.0, diferencia),
        "base_mensual_isr":   isr["base_mensual"],
    }
