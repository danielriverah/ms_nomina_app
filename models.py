"""
Modelos de base de datos - Sistema de Nómina Mega Fresh
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime

db = SQLAlchemy()


class Trabajador(db.Model):
    __tablename__ = "sn_trabajadores"

    trabajador_id  = db.Column(db.Integer, primary_key=True)
    imss           = db.Column(db.String(20), unique=True, nullable=False, index=True)
    rfc            = db.Column(db.String(15))
    curp           = db.Column(db.String(20))
    nombre         = db.Column(db.String(120), nullable=False)
    apellido_pat   = db.Column(db.String(60))
    apellido_mat   = db.Column(db.String(60))
    tipo_trabajador= db.Column(db.String(20), default="EVENTUAL")  # PERMANENTE / EVENTUAL
    area_funcional = db.Column(db.String(80))
    puesto         = db.Column(db.String(80))
    periodo_pago   = db.Column(db.String(20), default="SEMANAL")

    # Salarios
    salario_dia_real  = db.Column(db.Float, default=0.0)
    sbc_dia           = db.Column(db.Float, default=0.0)   # Salario Base Cotización
    sdi_dia           = db.Column(db.Float, default=0.0)   # SDI = SBC * factor
    factor_integracion= db.Column(db.Float, default=1.0493)
    costo_hr_extra    = db.Column(db.Float, default=30.0)  # 30, 35 o 60

    # Pago
    banco             = db.Column(db.String(40))
    num_cuenta        = db.Column(db.String(30))
    num_tarjeta       = db.Column(db.String(25))
    forma_pago        = db.Column(db.String(20), default="TARJETA")  # TARJETA / EFECTIVO

    # INFONAVIT
    credito_infonavit = db.Column(db.Float, default=0.0)
    factor_infonavit  = db.Column(db.Float, default=0.0)

    # Vacaciones
    vac_del_periodo   = db.Column(db.Integer, default=0)
    vac_acumuladas    = db.Column(db.Float, default=0.0)

    # Fechas
    fecha_ingreso_real = db.Column(db.Date)
    fecha_ingreso_imss = db.Column(db.Date)
    fecha_baja         = db.Column(db.Date)

    # Status
    estatus    = db.Column(db.String(20), default="ALTA")  # ALTA / BAJA / PENDIENTE
    tipo_baja  = db.Column(db.String(40))
    observaciones = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    incidencias = db.relationship("Incidencia", backref="trabajador", lazy=True)
    historiales = db.relationship("HistorialMovimiento", backref="trabajador", lazy=True)

    @property
    def nombre_completo(self):
        partes = [self.apellido_pat, self.apellido_mat, self.nombre]
        return " ".join(p for p in partes if p).upper()

    def to_dict(self):
        return {
            "id": self.trabajador_id,
            "trabajador_id": self.trabajador_id,
            "imss": self.imss,
            "rfc": self.rfc,
            "curp": self.curp,
            "nombre": self.nombre,
            "apellido_pat": self.apellido_pat,
            "apellido_mat": self.apellido_mat,
            "nombre_completo": self.nombre_completo,
            "tipo_trabajador": self.tipo_trabajador,
            "area_funcional": self.area_funcional,
            "puesto": self.puesto,
            "salario_dia_real": self.salario_dia_real,
            "sbc_dia": self.sbc_dia,
            "sdi_dia": self.sdi_dia,
            "factor_integracion": self.factor_integracion,
            "costo_hr_extra": self.costo_hr_extra,
            "banco": self.banco,
            "num_cuenta": self.num_cuenta,
            "num_tarjeta": self.num_tarjeta,
            "forma_pago": self.forma_pago,
            "credito_infonavit": self.credito_infonavit,
            "estatus": self.estatus,
            "fecha_ingreso_real": self.fecha_ingreso_real.isoformat() if self.fecha_ingreso_real else None,
            "fecha_ingreso_imss": self.fecha_ingreso_imss.isoformat() if self.fecha_ingreso_imss else None,
            "vac_del_periodo": self.vac_del_periodo,
        }


class HistorialMovimiento(db.Model):
    __tablename__ = "sn_historial_movimientos"

    historial_movimiento_id = db.Column(db.Integer, primary_key=True)
    trabajador_id = db.Column(db.Integer, db.ForeignKey("sn_trabajadores.trabajador_id"), nullable=False)
    tipo_movimiento = db.Column(db.String(20), nullable=False)  # ALTA / BAJA / REINGRESO / CAMBIO
    fecha_movimiento = db.Column(db.Date, nullable=False, default=date.today)
    riesgo_reingreso = db.Column(db.String(20), default="NORMAL")  # NORMAL / MEDIO / ALTO
    motivo = db.Column(db.String(250))
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por = db.Column(db.String(60))

    def to_dict(self):
        return {
            "historial_movimiento_id": self.historial_movimiento_id,
            "trabajador_id": self.trabajador_id,
            "tipo_movimiento": self.tipo_movimiento,
            "fecha_movimiento": self.fecha_movimiento.isoformat() if self.fecha_movimiento else None,
            "riesgo_reingreso": self.riesgo_reingreso,
            "motivo": self.motivo,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "creado_por": self.creado_por,
        }


class PeriodoNomina(db.Model):
    __tablename__ = "sn_periodos_nomina"

    periodo_nomina_id = db.Column(db.Integer, primary_key=True)
    num_semana    = db.Column(db.Integer, nullable=False)
    anio          = db.Column(db.Integer, nullable=False)
    fecha_inicio  = db.Column(db.Date, nullable=False)
    fecha_fin     = db.Column(db.Date, nullable=False)
    fecha_pago    = db.Column(db.Date, nullable=False)
    estatus       = db.Column(db.String(20), default="ABIERTO")  # ABIERTO / CALCULADO / CERRADO
    uma_vigente   = db.Column(db.Float, default=117.31)
    sm_vigente    = db.Column(db.Float, default=315.04)
    se_decreto    = db.Column(db.Float, default=535.65)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    created_by    = db.Column(db.String(60))

    incidencias   = db.relationship("Incidencia", backref="periodo", lazy=True)

    def to_dict(self):
        return {
            "id": self.periodo_nomina_id,
            "periodo_nomina_id": self.periodo_nomina_id,
            "num_semana": self.num_semana,
            "anio": self.anio,
            "fecha_inicio": self.fecha_inicio.isoformat(),
            "fecha_fin": self.fecha_fin.isoformat(),
            "fecha_pago": self.fecha_pago.isoformat(),
            "estatus": self.estatus,
            "uma_vigente": self.uma_vigente,
            "sm_vigente": self.sm_vigente,
            "se_decreto": self.se_decreto,
        }


class Incidencia(db.Model):
    __tablename__ = "sn_incidencias"

    incidencia_id    = db.Column(db.Integer, primary_key=True)
    periodo_nomina_id = db.Column(db.Integer, db.ForeignKey("sn_periodos_nomina.periodo_nomina_id"), nullable=False)
    trabajador_id    = db.Column(db.Integer, db.ForeignKey("sn_trabajadores.trabajador_id"), nullable=False)

    # Incidencias capturadas
    dias_trabajados  = db.Column(db.Integer, default=0)
    dias_incapacidad = db.Column(db.Integer, default=0)
    tiene_bono       = db.Column(db.Boolean, default=False)
    horas_extras_reales  = db.Column(db.Float, default=0.0)
    horas_extras_fiscales= db.Column(db.Float, default=0.0)
    vacaciones_dias  = db.Column(db.Integer, default=0)
    prima_vac_dias   = db.Column(db.Integer, default=0)
    despensa         = db.Column(db.Float, default=0.0)
    asistencia       = db.Column(db.Float, default=0.0)
    puntualidad      = db.Column(db.Float, default=0.0)
    compensacion     = db.Column(db.Float, default=0.0)
    observacion      = db.Column(db.String(200))

    # Resultados calculados (se llenan al procesar)
    calculado        = db.Column(db.Boolean, default=False)

    # Fiscal
    sueldo_fiscal    = db.Column(db.Float, default=0.0)
    bono_fiscal      = db.Column(db.Float, default=0.0)
    hrs_extra_fiscal = db.Column(db.Float, default=0.0)
    vacaciones_fiscal= db.Column(db.Float, default=0.0)
    prima_vac_fiscal = db.Column(db.Float, default=0.0)
    suma_fiscal      = db.Column(db.Float, default=0.0)
    cuota_obrera     = db.Column(db.Float, default=0.0)
    isr_calcula      = db.Column(db.Float, default=0.0)
    sub_emp_acre     = db.Column(db.Float, default=0.0)
    isr_neto         = db.Column(db.Float, default=0.0)
    infonavit        = db.Column(db.Float, default=0.0)
    suma_deduc       = db.Column(db.Float, default=0.0)
    neto_fiscal      = db.Column(db.Float, default=0.0)

    # Real
    suma_real        = db.Column(db.Float, default=0.0)
    neto_real        = db.Column(db.Float, default=0.0)
    diferencia       = db.Column(db.Float, default=0.0)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(60))

    def to_dict(self):
        t = self.trabajador
        return {
            "id": self.incidencia_id,
            "incidencia_id": self.incidencia_id,
            "trabajador_id": self.trabajador_id,
            "periodo_nomina_id": self.periodo_nomina_id,
            "nombre_completo": t.nombre_completo if t else "",
            "nss": t.imss if t else "",
            "tipo_trabajador": t.tipo_trabajador if t else "",
            "area_funcional": t.area_funcional if t else "",
            "puesto": t.puesto if t else "",
            "sbc_dia": t.sbc_dia if t else 0,
            "salario_dia_real": t.salario_dia_real if t else 0,
            "forma_pago": t.forma_pago if t else "TARJETA",
            "dias_trabajados": self.dias_trabajados,
            "dias_incapacidad": self.dias_incapacidad,
            "tiene_bono": self.tiene_bono,
            "horas_extras_reales": self.horas_extras_reales,
            "horas_extras_fiscales": self.horas_extras_fiscales,
            "vacaciones_dias": self.vacaciones_dias,
            "despensa": self.despensa,
            "asistencia": self.asistencia,
            "puntualidad": self.puntualidad,
            "compensacion": self.compensacion,
            "observacion": self.observacion,
            "calculado": self.calculado,
            "sueldo_fiscal": self.sueldo_fiscal,
            "bono_fiscal": self.bono_fiscal,
            "hrs_extra_fiscal": self.hrs_extra_fiscal,
            "vacaciones_fiscal": self.vacaciones_fiscal,
            "prima_vac_fiscal": self.prima_vac_fiscal,
            "suma_fiscal": self.suma_fiscal,
            "cuota_obrera": self.cuota_obrera,
            "isr_calcula": self.isr_calcula,
            "sub_emp_acre": self.sub_emp_acre,
            "isr_neto": self.isr_neto,
            "infonavit": self.infonavit,
            "suma_deduc": self.suma_deduc,
            "neto_fiscal": self.neto_fiscal,
            "suma_real": self.suma_real,
            "neto_real": self.neto_real,
            "diferencia": self.diferencia,
        }
