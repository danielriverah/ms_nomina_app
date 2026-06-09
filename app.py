"""
Sistema de Nómina Semanal — Mega Fresh Produce
Flask web application
"""
import os, json
import traceback
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
import pandas as pd
import io

from dotenv import load_dotenv

from models import db, Trabajador, PeriodoNomina, Incidencia
from calculos import calcular_nomina_trabajador, get_decreto_se, UMA_DIA, SM_DIA
from exportar import generar_nomina_topes

load_dotenv()


def build_database_uri():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    db_dialect = os.environ.get("DB_DIALECT", "").strip().lower()
    if db_dialect == "mysql":
        db_user = os.environ.get("DB_USER", "")
        db_password = os.environ.get("DB_PASSWORD", "")
        db_host = os.environ.get("DB_HOST", "")
        db_port = os.environ.get("DB_PORT", "3306")
        db_name = os.environ.get("DB_NAME", "")
        db_driver = os.environ.get("DB_DRIVER", "pymysql").strip()
        if all([db_user, db_password, db_host, db_name]):
            return f"mysql+{db_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    return os.environ.get("SQLITE_URL", "sqlite:///nomina.db")


# ─────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mfp-nomina-2026-dev")
app.config["SQLALCHEMY_DATABASE_URI"] = build_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
app.config["DB_INIT_ERROR"] = None
app.config["DB_INIT_ERROR_SHORT"] = None

if os.environ.get("AUTO_CREATE_TABLES", "").strip().lower() in ("1", "true", "yes", "on"):
    with app.app_context():
        try:
            db.create_all()
        except Exception as exc:
            app.config["DB_INIT_ERROR"] = traceback.format_exc()
            app.config["DB_INIT_ERROR_SHORT"] = str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# RUTAS PRINCIPALES
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if app.config.get("DB_INIT_ERROR_SHORT"):
        return (
            "Error de base de datos al iniciar la app: "
            + app.config["DB_INIT_ERROR_SHORT"],
            500,
        )
    return render_template("index.html")


@app.route("/api/startup-error")
def startup_error():
    if not app.config.get("DB_INIT_ERROR"):
        return jsonify({"ok": True, "error": None})
    return jsonify(
        {
            "ok": False,
            "error": app.config["DB_INIT_ERROR_SHORT"],
            "traceback": app.config["DB_INIT_ERROR"],
        }
    ), 500


# ──────────────────────────────────────────────────────────────────────────────
# TRABAJADORES
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/trabajadores", methods=["GET"])
def get_trabajadores():
    q = request.args.get("q", "").strip()
    estatus = request.args.get("estatus", "ALTA")
    tipo = request.args.get("tipo", "")

    query = Trabajador.query
    if estatus:
        query = query.filter(Trabajador.estatus == estatus)
    if tipo:
        query = query.filter(Trabajador.tipo_trabajador == tipo)
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(
            db.or_(
                Trabajador.nombre.ilike(like),
                Trabajador.apellido_pat.ilike(like),
                Trabajador.imss.like(f"%{q}%"),
                Trabajador.rfc.ilike(like),
            )
        )
    trabas = query.order_by(Trabajador.apellido_pat, Trabajador.nombre).all()
    return jsonify([t.to_dict() for t in trabas])


@app.route("/api/trabajadores/<int:tid>", methods=["GET"])
def get_trabajador(tid):
    t = Trabajador.query.get_or_404(tid)
    return jsonify(t.to_dict())


@app.route("/api/trabajadores", methods=["POST"])
def crear_trabajador():
    data = request.json
    # Validar NSS único
    existing = Trabajador.query.filter_by(imss=data.get("imss")).first()
    if existing:
        return jsonify({"error": f"NSS {data['imss']} ya existe en el sistema"}), 400

    t = Trabajador(
        imss=data["imss"],
        rfc=data.get("rfc", ""),
        curp=data.get("curp", ""),
        nombre=data["nombre"].upper(),
        apellido_pat=data.get("apellido_pat", "").upper(),
        apellido_mat=data.get("apellido_mat", "").upper(),
        tipo_trabajador=data.get("tipo_trabajador", "EVENTUAL"),
        area_funcional=data.get("area_funcional", ""),
        puesto=data.get("puesto", ""),
        salario_dia_real=float(data.get("salario_dia_real", 0)),
        sbc_dia=float(data.get("sbc_dia", 0)),
        sdi_dia=float(data.get("sdi_dia", 0)),
        factor_integracion=float(data.get("factor_integracion", 1.0493)),
        costo_hr_extra=float(data.get("costo_hr_extra", 30)),
        banco=data.get("banco", ""),
        num_cuenta=data.get("num_cuenta", ""),
        num_tarjeta=data.get("num_tarjeta", ""),
        forma_pago=data.get("forma_pago", "TARJETA"),
        credito_infonavit=float(data.get("credito_infonavit", 0)),
        factor_infonavit=float(data.get("factor_infonavit", 0)),
        vac_del_periodo=int(data.get("vac_del_periodo", 0)),
        estatus="ALTA",
        observaciones=data.get("observaciones", ""),
    )
    if data.get("fecha_ingreso_real"):
        t.fecha_ingreso_real = date.fromisoformat(data["fecha_ingreso_real"])
    if data.get("fecha_ingreso_imss"):
        t.fecha_ingreso_imss = date.fromisoformat(data["fecha_ingreso_imss"])

    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@app.route("/api/trabajadores/<int:tid>", methods=["PUT"])
def actualizar_trabajador(tid):
    t = Trabajador.query.get_or_404(tid)
    data = request.json
    campos = [
        "rfc","curp","nombre","apellido_pat","apellido_mat","tipo_trabajador",
        "area_funcional","puesto","salario_dia_real","sbc_dia","sdi_dia",
        "factor_integracion","costo_hr_extra","banco","num_cuenta","num_tarjeta",
        "forma_pago","credito_infonavit","factor_infonavit","vac_del_periodo",
        "observaciones"
    ]
    for campo in campos:
        if campo in data:
            val = data[campo]
            if campo in ("nombre","apellido_pat","apellido_mat","puesto","area_funcional"):
                val = val.upper() if val else val
            setattr(t, campo, val)
    if "fecha_ingreso_real" in data and data["fecha_ingreso_real"]:
        t.fecha_ingreso_real = date.fromisoformat(data["fecha_ingreso_real"])
    if "fecha_ingreso_imss" in data and data["fecha_ingreso_imss"]:
        t.fecha_ingreso_imss = date.fromisoformat(data["fecha_ingreso_imss"])
    t.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(t.to_dict())


@app.route("/api/trabajadores/<int:tid>/baja", methods=["POST"])
def dar_baja_trabajador(tid):
    t = Trabajador.query.get_or_404(tid)
    data = request.json
    t.estatus = "BAJA"
    t.tipo_baja = data.get("tipo_baja", "")
    t.fecha_baja = date.fromisoformat(data["fecha_baja"]) if data.get("fecha_baja") else date.today()
    t.observaciones = (t.observaciones or "") + f" | BAJA: {data.get('motivo','')}"
    t.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "mensaje": f"{t.nombre_completo} dado de baja"})


@app.route("/api/trabajadores/importar", methods=["POST"])
def importar_trabajadores():
    """Importa trabajadores desde Excel BDA."""
    if "file" not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400
    f = request.files["file"]
    try:
        bda = pd.read_excel(f, sheet_name="BDA MFP", header=4, engine="pyxlsb")
        activos = bda[bda["ESTATUS"].astype(str).str.strip().str.upper() == "ALTA"]
        creados = 0
        actualizados = 0
        errores = []
        for _, row in activos.iterrows():
            imss = str(row.get("IMSS", "")).strip().replace(".0","")
            if not imss or imss == "nan":
                continue
            try:
                existing = Trabajador.query.filter_by(imss=imss).first()
                nombre1 = str(row.get(" NOMBRE 1", "")).strip()
                apellidos = nombre1.split(" ")
                apepat = apellidos[0] if apellidos else ""
                apemat = apellidos[1] if len(apellidos) > 1 else ""
                nombres = " ".join(apellidos[2:]) if len(apellidos) > 2 else nombre1

                if existing:
                    existing.sbc_dia = float(row.get("SAL. DIARIO IMSS (SD)", 0) or 0)
                    existing.sdi_dia = float(row.get("SAL. INTEG.", 0) or 0)
                    existing.factor_integracion = float(row.get("FACT. INTEG.", 1.0493) or 1.0493)
                    existing.salario_dia_real = float(row.get("SALARIO DIARIO REAL", 0) or 0)
                    msd = str(row.get("MODIFICACION SDI 2026", "") or "")
                    if msd and msd != "nan":
                        parts = msd.replace("MDS ", "").strip().split()
                        if parts:
                            try:
                                existing.sbc_dia = float(parts[0]) if parts[0] else existing.sbc_dia
                            except: pass
                    actualizados += 1
                else:
                    t = Trabajador(
                        imss=imss,
                        rfc=str(row.get("RFC","") or "").strip(),
                        curp=str(row.get("CURP","") or "").strip(),
                        nombre=nombres.upper(),
                        apellido_pat=apepat.upper(),
                        apellido_mat=apemat.upper(),
                        tipo_trabajador=str(row.get("TIPO DE TRABAJADOR","EVENTUAL") or "EVENTUAL").upper().strip(),
                        area_funcional=str(row.get("AREAFUNCIONAL","") or "").strip(),
                        puesto=str(row.get("PUESTO","") or "").strip(),
                        salario_dia_real=float(row.get("SALARIO DIARIO REAL", 0) or 0),
                        sbc_dia=float(row.get("SAL. DIARIO IMSS (SD)", 0) or 0),
                        sdi_dia=float(row.get("SAL. INTEG.", 0) or 0),
                        factor_integracion=float(row.get("FACT. INTEG.", 1.0493) or 1.0493),
                        costo_hr_extra=float(row.get("TIEMPO EXTRA AUTRIZADO", 30) or 30),
                        banco=str(row.get("BANCO","") or "").strip(),
                        num_cuenta=str(row.get("NUM DE CTA","") or "").replace(".0","").strip(),
                        num_tarjeta=str(row.get("NUM DE TARJETA","") or "").replace(".0","").strip(),
                        forma_pago="TARJETA",
                        credito_infonavit=float(row.get("CREDITO INFONAVIT", 0) or 0),
                        factor_infonavit=float(row.get("FACTOR RENT INFONAVIT", 0) or 0),
                        estatus="ALTA",
                    )
                    if row.get("F. INGRESO REAL") and str(row["F. INGRESO REAL"]) != "nan":
                        try:
                            fi = pd.to_datetime(row["F. INGRESO REAL"])
                            t.fecha_ingreso_real = fi.date()
                        except: pass
                    if row.get("F. INGRESO IMSS") and str(row["F. INGRESO IMSS"]) != "nan":
                        try:
                            fi = pd.to_datetime(row["F. INGRESO IMSS"])
                            t.fecha_ingreso_imss = fi.date()
                        except: pass
                    db.session.add(t)
                    creados += 1
            except Exception as e:
                errores.append(f"NSS {imss}: {str(e)[:80]}")
        db.session.commit()
        return jsonify({
            "ok": True,
            "creados": creados,
            "actualizados": actualizados,
            "errores": errores[:20],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# PERÍODOS DE NÓMINA
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/periodos", methods=["GET"])
def get_periodos():
    periodos = PeriodoNomina.query.order_by(PeriodoNomina.fecha_pago.desc()).limit(20).all()
    return jsonify([p.to_dict() for p in periodos])


@app.route("/api/periodos", methods=["POST"])
def crear_periodo():
    data = request.json
    # Detectar SE decreto automáticamente
    fp = date.fromisoformat(data["fecha_pago"])
    se = get_decreto_se(fp)

    p = PeriodoNomina(
        num_semana=int(data["num_semana"]),
        anio=int(data["anio"]),
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]),
        fecha_fin=date.fromisoformat(data["fecha_fin"]),
        fecha_pago=fp,
        uma_vigente=float(data.get("uma_vigente", UMA_DIA)),
        sm_vigente=float(data.get("sm_vigente", SM_DIA)),
        se_decreto=se,
        created_by=data.get("usuario", "sistema"),
    )
    db.session.add(p)
    db.session.commit()

    # Crear incidencias vacías para todos los trabajadores activos
    trabas = Trabajador.query.filter_by(estatus="ALTA").all()
    for t in trabas:
        inc = Incidencia(
            periodo_nomina_id=p.periodo_nomina_id,
            trabajador_id=t.trabajador_id,
            dias_trabajados=7 if t.tipo_trabajador == "PERMANENTE" else 6,
            tiene_bono=True if t.tipo_trabajador == "PERMANENTE" else False,
        )
        db.session.add(inc)
    db.session.commit()

    return jsonify({**p.to_dict(), "incidencias_creadas": len(trabas)}), 201


@app.route("/api/periodos/<int:pid>", methods=["GET"])
def get_periodo(pid):
    p = PeriodoNomina.query.get_or_404(pid)
    return jsonify(p.to_dict())


# ──────────────────────────────────────────────────────────────────────────────
# INCIDENCIAS / CAPTURA
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/periodos/<int:pid>/incidencias", methods=["GET"])
def get_incidencias(pid):
    tipo = request.args.get("tipo", "")
    q    = request.args.get("q", "").strip()

    query = (
        Incidencia.query
        .join(Trabajador)
        .filter(Incidencia.periodo_nomina_id == pid)
        .filter(Trabajador.estatus == "ALTA")
    )
    if tipo:
        query = query.filter(Trabajador.tipo_trabajador == tipo)
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(
            db.or_(
                Trabajador.nombre.ilike(like),
                Trabajador.apellido_pat.ilike(like),
                Trabajador.imss.like(f"%{q}%"),
            )
        )
    incs = query.order_by(Trabajador.apellido_pat, Trabajador.nombre).all()
    return jsonify([i.to_dict() for i in incs])


@app.route("/api/incidencias/<int:iid>", methods=["PUT"])
def actualizar_incidencia(iid):
    inc = Incidencia.query.get_or_404(iid)
    data = request.json
    campos = [
        "dias_trabajados","dias_incapacidad","tiene_bono",
        "horas_extras_reales","horas_extras_fiscales",
        "vacaciones_dias","prima_vac_dias",
        "despensa","asistencia","puntualidad","compensacion","observacion",
    ]
    for campo in campos:
        if campo in data:
            setattr(inc, campo, data[campo])
    inc.calculado = False  # invalidar cálculo previo
    inc.updated_by = data.get("usuario", "sistema")
    db.session.commit()
    return jsonify(inc.to_dict())


@app.route("/api/incidencias/lote", methods=["PUT"])
def actualizar_incidencias_lote():
    """Actualiza múltiples incidencias en una sola llamada."""
    data = request.json  # lista de {id, campo: valor, ...}
    for item in data:
        iid = item.pop("id", None)
        if not iid:
            continue
        inc = Incidencia.query.get(iid)
        if not inc:
            continue
        for k, v in item.items():
            if hasattr(inc, k):
                setattr(inc, k, v)
        inc.calculado = False
    db.session.commit()
    return jsonify({"ok": True, "actualizados": len(data)})


# ──────────────────────────────────────────────────────────────────────────────
# CÁLCULO DE PRENÓMINA
# ──────────────────────────────────────────────────────────────────────────────

def _procesar_incidencia(inc: Incidencia, fecha_pago: date) -> dict:
    """Calcula la nómina para una incidencia y guarda resultados."""
    t = inc.trabajador
    resultado = calcular_nomina_trabajador(
        sbc_dia=t.sbc_dia,
        sd_real_dia=t.salario_dia_real,
        factor_integracion=t.factor_integracion or 1.0493,
        tipo_trabajador=t.tipo_trabajador,
        costo_hr_extra=t.costo_hr_extra or 30.0,
        credito_infonavit=t.credito_infonavit or 0.0,
        dias_trabajados=inc.dias_trabajados or 0,
        dias_incapacidad=inc.dias_incapacidad or 0,
        tiene_bono=bool(inc.tiene_bono),
        horas_extras_reales=inc.horas_extras_reales or 0.0,
        horas_extras_fiscales=inc.horas_extras_fiscales or 0.0,
        vacaciones_dias=inc.vacaciones_dias or 0,
        prima_vacacional_dias=inc.prima_vac_dias or 0,
        despensa=inc.despensa or 0.0,
        asistencia=inc.asistencia or 0.0,
        puntualidad=inc.puntualidad or 0.0,
        compensacion=inc.compensacion or 0.0,
        fecha_pago=fecha_pago,
    )

    # Guardar resultados en la incidencia
    inc.sueldo_fiscal    = resultado["sueldo_fiscal"]
    inc.bono_fiscal      = resultado["bono_fiscal"]
    inc.hrs_extra_fiscal = resultado["total_he_fiscal"]
    inc.vacaciones_fiscal= resultado["vacaciones_fiscal"]
    inc.prima_vac_fiscal = resultado["prima_vac_fiscal"]
    inc.suma_fiscal      = resultado["suma_fiscal"]
    inc.cuota_obrera     = resultado["cuota_obrera"]
    inc.isr_calcula      = resultado["isr_calcula"]
    inc.sub_emp_acre     = resultado["sub_emp_acre"]
    inc.isr_neto         = resultado["isr_neto"]
    inc.infonavit        = resultado["infonavit"]
    inc.suma_deduc       = resultado["suma_deduc"]
    inc.neto_fiscal      = resultado["neto_fiscal"]
    inc.suma_real        = resultado["suma_real"]
    inc.neto_real        = resultado["neto_real"]
    inc.diferencia       = resultado["diferencia"]
    inc.calculado        = True

    return resultado


@app.route("/api/periodos/<int:pid>/calcular", methods=["POST"])
def calcular_periodo(pid):
    """Calcula/recalcula la prenómina del período."""
    p = PeriodoNomina.query.get_or_404(pid)
    if p.estatus == "CERRADO":
        return jsonify({"error": "El período está cerrado"}), 400

    incidencias = Incidencia.query.filter_by(periodo_nomina_id=pid).all()
    procesados = 0
    errores = []

    for inc in incidencias:
        try:
            _procesar_incidencia(inc, p.fecha_pago)
            procesados += 1
        except Exception as e:
            errores.append(f"ID {inc.trabajador_id}: {str(e)[:80]}")

    p.estatus = "CALCULADO"
    db.session.commit()

    # Resumen rápido
    total_fiscal = sum(i.neto_fiscal or 0 for i in incidencias)
    total_real   = sum(i.neto_real   or 0 for i in incidencias)
    total_dif    = sum(i.diferencia  or 0 for i in incidencias)

    return jsonify({
        "ok": True,
        "procesados": procesados,
        "errores": errores[:10],
        "resumen": {
            "total_fiscal": round(total_fiscal, 2),
            "total_real":   round(total_real, 2),
            "total_diferencia": round(total_dif, 2),
        }
    })


@app.route("/api/periodos/<int:pid>/resumen", methods=["GET"])
def resumen_periodo(pid):
    p = PeriodoNomina.query.get_or_404(pid)
    incs = Incidencia.query.filter_by(periodo_nomina_id=pid).join(Trabajador).all()

    def agg(tipo=None):
        lst = [i for i in incs if (not tipo or i.trabajador.tipo_trabajador == tipo) and i.calculado]
        return {
            "trabajadores": len(lst),
            "suma_fiscal":  round(sum(i.suma_fiscal or 0 for i in lst), 2),
            "cuota_obrera": round(sum(i.cuota_obrera or 0 for i in lst), 2),
            "isr_neto":     round(sum(i.isr_neto or 0 for i in lst), 2),
            "sub_emp":      round(sum(i.sub_emp_acre or 0 for i in lst), 2),
            "infonavit":    round(sum(i.infonavit or 0 for i in lst), 2),
            "suma_deduc":   round(sum(i.suma_deduc or 0 for i in lst), 2),
            "neto_fiscal":  round(sum(i.neto_fiscal or 0 for i in lst), 2),
            "diferencia":   round(sum(i.diferencia or 0 for i in lst), 2),
            "neto_real":    round(sum(i.neto_real or 0 for i in lst), 2),
            "sin_calcular": len([i for i in incs if (not tipo or i.trabajador.tipo_trabajador == tipo) and not i.calculado]),
        }

    return jsonify({
        "periodo": p.to_dict(),
        "permanente": agg("PERMANENTE"),
        "eventual":   agg("EVENTUAL"),
        "total":      agg(),
    })


# ──────────────────────────────────────────────────────────────────────────────
# EXPORTACIÓN
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/periodos/<int:pid>/exportar", methods=["GET"])
def exportar_nomina(pid):
    p = PeriodoNomina.query.get_or_404(pid)
    tipo = request.args.get("tipo", "TODOS")  # PERMANENTE / EVENTUAL / TODOS

    incs_query = (
        Incidencia.query
        .join(Trabajador)
        .filter(Incidencia.periodo_nomina_id == pid, Incidencia.calculado == True)
    )
    if tipo != "TODOS":
        incs_query = incs_query.filter(Trabajador.tipo_trabajador == tipo)

    incs = incs_query.order_by(Trabajador.apellido_pat, Trabajador.nombre).all()

    if not incs:
        return jsonify({"error": "No hay incidencias calculadas"}), 400

    # Construir lista para el generador
    data = []
    for inc in incs:
        t = inc.trabajador
        resultado = {
            "sueldo_fiscal":    inc.sueldo_fiscal,
            "bono_fiscal":      inc.bono_fiscal,
            "total_he_fiscal":  inc.hrs_extra_fiscal,
            "exento_he":        0.0,
            "gravado_he":       inc.hrs_extra_fiscal,
            "vacaciones_fiscal":inc.vacaciones_fiscal,
            "exento_vac":       0.0,
            "prima_vac_fiscal": inc.prima_vac_fiscal,
            "exento_prima_vac": 0.0,
            "despensa":         inc.despensa or 0,
            "asistencia":       inc.asistencia or 0,
            "puntualidad":      inc.puntualidad or 0,
            "compensacion":     inc.compensacion or 0,
            "suma_fiscal":      inc.suma_fiscal,
            "cuota_obrera":     inc.cuota_obrera,
            "isr_calcula":      inc.isr_calcula,
            "sub_emp_acre":     inc.sub_emp_acre,
            "isr_neto":         inc.isr_neto,
            "sub_emp_neto":     0.0,
            "infonavit":        inc.infonavit,
            "suma_deduc":       inc.suma_deduc,
            "neto_fiscal":      inc.neto_fiscal,
            "suma_real":        inc.suma_real,
            "neto_real":        inc.neto_real,
            "diferencia":       inc.diferencia,
        }
        data.append({
            "trabajador": {**t.to_dict(), "factor_integracion": t.factor_integracion},
            "resultado": resultado,
            "dias_trabajados": inc.dias_trabajados,
            "dias_incapacidad": inc.dias_incapacidad,
            "horas_extras_fiscales": inc.horas_extras_fiscales,
            "observacion": inc.observacion,
        })

    periodo_dict = {
        **p.to_dict(),
        "fecha_inicio": p.fecha_inicio.strftime("%d/%m/%Y"),
        "fecha_fin":    p.fecha_fin.strftime("%d/%m/%Y"),
        "fecha_pago":   p.fecha_pago.strftime("%d/%m/%Y"),
    }

    excel_bytes = generar_nomina_topes(periodo_dict, data, tipo if tipo != "TODOS" else "TODOS")

    filename = f"NOMINA_SEM{p.num_semana}_{p.anio}_{tipo}.xlsx"
    return send_file(
        io.BytesIO(excel_bytes),
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/periodos/<int:pid>/cerrar", methods=["POST"])
def cerrar_periodo(pid):
    p = PeriodoNomina.query.get_or_404(pid)
    if p.estatus != "CALCULADO":
        return jsonify({"error": "Debe calcular la nómina antes de cerrar"}), 400
    p.estatus = "CERRADO"
    db.session.commit()
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────────────────────────
# CATÁLOGOS
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/catalogos/areas", methods=["GET"])
def get_areas():
    areas = db.session.query(Trabajador.area_funcional).filter(
        Trabajador.area_funcional != None, Trabajador.estatus == "ALTA"
    ).distinct().order_by(Trabajador.area_funcional).all()
    return jsonify([a[0] for a in areas if a[0]])


@app.route("/api/catalogos/puestos", methods=["GET"])
def get_puestos():
    puestos = db.session.query(Trabajador.puesto).filter(
        Trabajador.puesto != None, Trabajador.estatus == "ALTA"
    ).distinct().order_by(Trabajador.puesto).all()
    return jsonify([p[0] for p in puestos if p[0]])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
