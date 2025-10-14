# analyze_results_streamlit_secure.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from fpdf import FPDF
from datetime import datetime
import requests, json, csv, io, re
from pathlib import Path

from analyze_results_sqlite import (
    load_data, init_db, insert_result, DB_PATH, next_student_seq_for_exam
)

# Estilos
from styles import apply_css, TOKENS

USERS = {"admin": "admin123", "profesor": "clave2025"}
N8N_WEBHOOK_URL = "https://mari25.app.n8n.cloud/webhook-test/exam-auto-grader"

st.set_page_config(page_title="AutoGrader | Panel", page_icon="📘", layout="wide")
apply_css(TOKENS)

# ---------- Utilidades ----------
def _pdf_safe(text: str) -> str:
    return ''.join(ch for ch in text if ord(ch) <= 0xFFFF and ch != '\uFE0F')

def norm_value(v: str) -> str:
    if v is None: return ""
    s = str(v).strip().upper()
    if s in ("✔","✓","TRUE","T","SI","SÍ","YES"): return "V"
    if s in ("✘","X","FALSE","F","NO"):            return "F"
    return s

def _clean_q(x):
    if x is None: return None
    s = str(x).strip()
    s = re.sub(r"[^0-9]", "", s)
    return s if s.isdigit() else None

def parse_answer_key_csv(file) -> dict:
    raw = file.read()
    text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else str(raw)

    sample = text[:2048]
    candidates = [",",";","\t","|"]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(candidates))
        delim = dialect.delimiter
    except Exception:
        delim = ";" if sample.count(";")>sample.count(",") else ","

    buf = io.StringIO(text)
    # 1) con cabeceras
    try:
        reader = csv.DictReader(buf, delimiter=delim)
        rows = list(reader)
        if rows and rows[0]:
            mapping = {}
            for r in rows:
                q = (r.get("q") or r.get("question") or r.get("numero") or
                     r.get("pregunta") or r.get("n") or r.get("num") or r.get("id"))
                v = (r.get("value") or r.get("correct") or r.get("answer") or
                     r.get("respuesta") or r.get("alternativa") or r.get("val"))
                q = _clean_q(q)
                if q and v:
                    mapping[q] = norm_value(v)
            if mapping:
                return mapping
    except Exception:
        pass

    # 2) sin cabeceras
    buf.seek(0)
    mapping = {}
    for row in csv.reader(buf, delimiter=delim):
        if not row: continue
        if len(row) == 1:
            token = row[0].strip().replace("-", ":").replace("\t", ":").replace("|", ":")
            parts = [p.strip() for p in token.split(":") if p.strip()]
            if len(parts) >= 2 and _clean_q(parts[0]):
                mapping[_clean_q(parts[0])] = norm_value(parts[1])
        else:
            q = _clean_q(row[0])
            v = row[1].strip() if len(row) > 1 else ""
            if q and v:
                mapping[q] = norm_value(v)
    return mapping

def safe_parse_answer_key_json(txt: str):
    if not txt: return None
    t = txt.strip()
    try:
        return json.loads(t)
    except Exception:
        try:
            return json.loads(t.replace("'", '"'))
        except Exception:
            return None

def slugify_exam_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s or "examen"

def explode_answers(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        try:
            aj = r.get("answers_json")
            if pd.notna(aj) and str(aj).strip() != "":
                arr = json.loads(aj)
                for a in arr or []:
                    rows.append({
                        "timestamp": r["timestamp"],
                        "exam_id": r["exam_id"],
                        "student_id": r["student_id"],
                        "q": a.get("q") or a.get("question"),
                        "studentValue": a.get("value") or a.get("studentValue"),
                        "correctValue": a.get("correctValue"),
                        "isCorrect": a.get("isCorrect")
                    })
        except Exception:
            continue
    return pd.DataFrame(rows)

# ---------- Login (sin inputs vacíos) ----------
def autenticar_usuario():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        # CARD centrada
        st.markdown('<div class="auth-wrap">', unsafe_allow_html=True)
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        st.markdown('<div class="auth-title"><h2>Login</h2></div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-body">', unsafe_allow_html=True)

        # Campos (apilados como en la captura)
        user = st.text_input("Email / Usuario", key="lg_user")
        password = st.text_input("Password", type="password", key="lg_pass")

        st.markdown('</div>', unsafe_allow_html=True)  # /auth-body

        # Botón submit (dentro del card)
        st.markdown('<div class="auth-actions">', unsafe_allow_html=True)
        ok = st.button("Submit", type="primary")
        st.markdown('</div>', unsafe_allow_html=True)  # /auth-actions

        st.markdown('</div>', unsafe_allow_html=True)  # /auth-card
        st.markdown('</div>', unsafe_allow_html=True)  # /auth-wrap


        # Lógica de auth
        if ok:
            if user in USERS and USERS[user] == password:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Credenciales incorrectas.")
        st.stop()

    # Barra lateral cuando ya está logueado
    st.sidebar.markdown(f"**👤 Usuario:** {st.session_state.user}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.logged_in = False
        st.rerun()


# ---------- Modal Nueva evaluación ----------
def _form_contenido():
    st.write("Sube la **hoja de respuestas** (PDF o imagen) y la **plantilla (CSV o JSON)** para corregir.")

    mode = st.radio("¿Cómo subirás la plantilla de respuestas correctas?",
                    ["CSV", "JSON manual"], horizontal=True)
    answer_key_obj = None

    if mode == "CSV":
        csv_file = st.file_uploader("📄 CSV de la clave (q,value)", type=["csv"])
        if csv_file is not None:
            try:
                answer_key_obj = parse_answer_key_csv(io.BytesIO(csv_file.getvalue()))
                if not answer_key_obj:
                    st.error("CSV sin filas válidas. Usa columnas q/value o question/correct.")
                else:
                    st.success(f"Se cargaron {len(answer_key_obj)} claves desde el CSV.")
            except Exception as e:
                st.error(f"Error leyendo CSV: {e}")
    else:
        answer_key_text = st.text_area("Plantilla JSON (ej: {'1':'A','2':'C'})",
                                       value='{"1":"A","2":"C","3":"V"}', height=120)
        answer_key_obj = safe_parse_answer_key_json(answer_key_text)
        if answer_key_obj is None or not isinstance(answer_key_obj, dict):
            st.info("Ingresa JSON válido con formato {'1':'A','2':'C',...}")

    exam_file = st.file_uploader("📄 Examen (PDF o imagen: jpg/png)",
                                 type=["pdf", "jpg", "jpeg", "png"])

    if exam_file is not None:
        preview_exam = slugify_exam_name(Path(exam_file.name).stem)
        st.caption(f"Detectado exam_id: `{preview_exam}` (student_id se enumerará: est01, est02, …)")

    if st.button("Enviar para corrección", type="primary", use_container_width=True):
        if not exam_file:
            st.warning("Debes subir un archivo (PDF o imagen)."); st.stop()
        if not isinstance(answer_key_obj, dict) or not answer_key_obj:
            st.error("La plantilla (answer_key) es inválida o está vacía."); st.stop()

        stem = Path(exam_file.name).stem
        exam_id = slugify_exam_name(stem)
        try:
            seq = next_student_seq_for_exam(exam_id)
        except Exception:
            seq = 1
        student_id = f"est{seq:02d}"

        file_bytes = exam_file.getvalue()
        mime = (exam_file.type or "").lower()
        files = {
            'exam_file': (
                exam_file.name,
                file_bytes,
                mime if mime in ["application/pdf", "image/jpeg", "image/png"] else "application/octet-stream"
            )
        }
        data = {
            'student_id': student_id,
            'exam_id': exam_id,
            'answer_key': json.dumps(answer_key_obj)
        }

        try:
            resp = requests.post(N8N_WEBHOOK_URL, data=data, files=files, timeout=90)
            if resp.status_code != 200:
                st.error(f"Error {resp.status_code}: {resp.text}"); st.stop()
            ct = (resp.headers.get("Content-Type") or "").lower()
            if "application/json" in ct:
                result = resp.json()
            else:
                result = json.loads(resp.text)

            st.success(f"Corregido · exam_id: `{exam_id}` · student_id: `{student_id}`")

            answers_detail = result.get("answers", [])
            correct = result.get("correct_count")
            incorrect = result.get("incorrect_count")
            answered_count = result.get("answered_count")
            omitted_count = result.get("omitted_count")
            percent = result.get("percent_correct")

            if answers_detail and (answered_count is None or omitted_count is None or correct is None or incorrect is None or percent is None):
                det = []
                for a in answers_detail:
                    q = a.get("q") or a.get("question")
                    sv = a.get("value") or a.get("studentValue")
                    cv = a.get("correctValue")
                    ic = a.get("isCorrect")
                    det.append({"q": q, "studentValue": sv, "correctValue": cv,
                                "isCorrect": bool(ic) if ic is not None else (
                                    str(sv).upper()==str(cv).upper() if (sv and cv) else False)})
                answered_count = sum(1 for d in det if d["studentValue"] is not None)
                correct = sum(1 for d in det if d["isCorrect"])
                incorrect = answered_count - correct
                percent = round((correct/answered_count)*100, 2) if answered_count else 0.0
                omitted_count = omitted_count if omitted_count is not None else 0
                answers_detail = det

            insert_result(
                student_id=result.get("student_id", student_id),
                exam_id=result.get("exam_id", exam_id),
                correct=correct or 0,
                incorrect=incorrect or 0,
                percent=percent or 0.0,
                timestamp=datetime.now().isoformat(),
                answered_count=answered_count or 0,
                omitted_count=omitted_count or 0,
                answers_json=json.dumps(answers_detail or [])
            )
            st.toast("Resultado guardado y dashboard actualizado", icon="✅")
            st.session_state["_refresh"] = True
            st.rerun()
        except Exception as e:
            st.error(f"Fallo al comunicarse con n8n: {e}")

def boton_modal():
    open_modal_btn = st.button("➕ Nueva evaluación", type="primary")
    if hasattr(st, "dialog"):
        @st.dialog("Nueva evaluación")
        def _modal():
            _form_contenido()
        if open_modal_btn:
            _modal()
    else:
        if "show_modal" not in st.session_state: st.session_state.show_modal = False
        if open_modal_btn: st.session_state.show_modal = True
        if st.session_state.show_modal:
            st.markdown("""
            <div style="position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;display:flex;align-items:center;justify-content:center;">
              <div style="width:min(760px,95vw);background:#fff;border-radius:14px;padding:20px;box-shadow:0 30px 70px rgba(0,0,0,.35);">
            """, unsafe_allow_html=True)
            _form_contenido()
            if st.button("Cerrar", use_container_width=True):
                st.session_state.show_modal = False; st.rerun()
            st.markdown("</div></div>", unsafe_allow_html=True)

# ---------- Exportadores ----------
def export_pdf(df, stats, fig_buffer) -> BytesIO:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(13,71,161)
    pdf.cell(0, 12, _pdf_safe("AutoGrader - Reporte de Evaluaciones"), ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Arial", "", 11)
    pdf.set_text_color(0,0,0)
    pdf.cell(0, 7, _pdf_safe(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True)
    pdf.ln(4)

    for k, v in stats.items():
        pdf.cell(0, 7, _pdf_safe(f"{k}: {v}"), ln=True)
    pdf.ln(4)

    pdf.image(fig_buffer, x=15, w=180, type="PNG")

    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, _pdf_safe("Resultados"), ln=True)
    pdf.set_font("Arial", "", 10)
    headers = ["Fecha", "Examen", "Estudiante", "% Acierto", "Correctas", "Incorrectas"]
    col_w = [36, 40, 35, 25, 25, 25]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, _pdf_safe(h), border=1, align="C")
    pdf.ln(8)

    for _, r in df.iterrows():
        row = [
            str(r["timestamp"])[:16],
            str(r["exam_id"]),
            str(r["student_id"]),
            f'{float(r["percent_correct"]):.2f}',
            str(int(r.get("correct_count") or 0)),
            str(int(r.get("incorrect_count") or 0)),
        ]
        for i, cell in enumerate(row):
            pdf.cell(col_w[i], 8, _pdf_safe(cell), border=1)
        pdf.ln(8)

    out = BytesIO()
    pdf.output(out); out.seek(0)
    return out

def make_exports(df_filtered: pd.DataFrame):
    stats = {
        "Total registros": len(df_filtered),
        "Máximo (%)": round(df_filtered["percent_correct"].max(), 2),
        "Mínimo (%)": round(df_filtered["percent_correct"].min(), 2),
    }

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(df_filtered["percent_correct"], bins=10, edgecolor="black")
    axes[0].set_title("Distribución de porcentajes de aciertos")
    axes[0].set_xlabel("Porcentaje de aciertos")
    axes[0].set_ylabel("Frecuencia")

    df_sorted = df_filtered.sort_values("percent_correct", ascending=False)
    axes[1].bar(df_sorted["student_id"], df_sorted["percent_correct"])
    axes[1].set_title("Desempeño por estudiante")
    axes[1].set_xlabel("Estudiante")
    axes[1].set_ylabel("Porcentaje (%)")
    axes[1].tick_params(axis="x", rotation=45)
    plt.tight_layout()

    fig_buf = BytesIO()
    fig.savefig(fig_buf, format="png", dpi=150); fig_buf.seek(0)

    pdf_bytes = export_pdf(df_filtered, stats, fig_buf)

    csv_results = df_filtered.to_csv(index=False).encode("utf-8")
    detail_df = explode_answers(df_filtered)
    csv_detail = detail_df.to_csv(index=False).encode("utf-8")

    xls_buf = BytesIO()
    with pd.ExcelWriter(xls_buf, engine="xlsxwriter") as writer:
        pd.DataFrame([stats]).to_excel(writer, sheet_name="Resumen", index=False)
        df_filtered.to_excel(writer, sheet_name="Resultados", index=False)
        detail_df.to_excel(writer, sheet_name="DetallePreguntas", index=False)
    xls_buf.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return {
        "pdf": (pdf_bytes, f"reporte_{timestamp}.pdf"),
        "csv_results": (csv_results, f"resultados_{timestamp}.csv"),
        "csv_detail": (csv_detail, f"detalle_preguntas_{timestamp}.csv"),
        "xlsx": (xls_buf, f"resultados_{timestamp}.xlsx"),
    }

# ---------- App ----------
def main():
    autenticar_usuario()

    st.markdown("""
    <div class="header-box">
      <h1>AutoGrader · Panel principal</h1>
      <p>Visualiza, filtra y descarga reportes de evaluaciones</p>
    </div>""", unsafe_allow_html=True)

    # Sidebar: título + card (sin inputs vacíos)
    st.sidebar.markdown(f'<div class="sidebar-title">🔎 Filtros</div>', unsafe_allow_html=True)

    # Botón / modal
    boton_modal()

    # BD
    try:
        init_db()
    except Exception as e:
        st.error(f"No se pudo inicializar la BD en {DB_PATH}: {e}")
        st.stop()

    try:
        df = load_data()
    except Exception as e:
        st.error(f"Error al leer la base de datos: {e}")
        st.stop()

    if df.empty:
        st.info("Aún no hay registros. Carga tu primera evaluación desde “Nueva evaluación”.")
        st.sidebar.markdown('</div>', unsafe_allow_html=True)
        st.stop()

    # Filtros reales
    exams = sorted(df["exam_id"].unique().tolist())
    exam_filter = st.sidebar.multiselect("Examen", exams, default=exams)

    students_pool = df[df["exam_id"].isin(exam_filter)]["student_id"].unique().tolist()
    student_filter = st.sidebar.multiselect("Estudiante (opcional)", sorted(students_pool), default=[])

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    dmin, dmax = df["timestamp"].min().date(), df["timestamp"].max().date()
    date_range = st.sidebar.date_input("Rango de fechas", (dmin, dmax), min_value=dmin, max_value=dmax)

    st.sidebar.markdown('</div>', unsafe_allow_html=True)

    df_filtered = df[(df["exam_id"].isin(exam_filter)) &
                     (df["timestamp"].dt.date >= date_range[0]) &
                     (df["timestamp"].dt.date <= date_range[1])]
    if student_filter:
        df_filtered = df_filtered[df_filtered["student_id"].isin(student_filter)]

    if df_filtered.empty:
        st.warning("No hay resultados que coincidan con los filtros."); st.stop()

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Resumen", "🧑‍🎓 Exámenes y estudiantes", "📄 Datos & Exportar"])

    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="kpi"><h4>Registros</h4><div class="val">{len(df_filtered)}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="kpi"><h4>Máximo (%)</h4><div class="val">{df_filtered["percent_correct"].max():.2f}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="kpi"><h4>Mínimo (%)</h4><div class="val">{df_filtered["percent_correct"].min():.2f}</div></div>', unsafe_allow_html=True)

        plt.style.use("seaborn-v0_8-whitegrid")
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        axes[0].hist(df_filtered["percent_correct"], bins=10, edgecolor="black")
        axes[0].set_title("Distribución de porcentajes de aciertos"); axes[0].set_xlabel("Porcentaje"); axes[0].set_ylabel("Frecuencia")

        df_sorted = df_filtered.sort_values("percent_correct", ascending=False)
        axes[1].bar(df_sorted["student_id"], df_sorted["percent_correct"])
        axes[1].set_title("Ranking de desempeño"); axes[1].set_xlabel("Estudiante"); axes[1].set_ylabel("Porcentaje (%)")
        axes[1].tick_params(axis="x", rotation=45)
        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)

    with tab2:
        st.subheader("Estudiantes por Examen")
        summary = (
            df
            .groupby("exam_id", as_index=False)
            .agg(estudiantes=("student_id", lambda s: ", ".join(sorted(set(s)))),
                 conteo=("student_id", "nunique"))
            .sort_values("exam_id")
        )
        st.dataframe(summary, use_container_width=True)

        st.subheader("Detalle por Examen y Estudiante")
        for ex_id, sub in df.sort_values(["exam_id","timestamp"]).groupby("exam_id"):
            with st.expander(f"Examen: {ex_id} · Registros: {len(sub)} · Estudiantes: {sub['student_id'].nunique()}"):
                for sid, srows in sub.sort_values("timestamp").groupby("student_id"):
                    row = srows.iloc[-1]
                    correct = int(row.get("correct_count") or 0)
                    incorrect = int(row.get("incorrect_count") or 0)
                    answered = int(row.get("answered_count") or 0)
                    omitted = int(row.get("omitted_count") or 0)
                    percent = float(row.get("percent_correct") or 0.0)

                    answers_detail = []
                    try:
                        aj = row.get("answers_json")
                        if pd.notna(aj) and str(aj).strip() != "":
                            answers_detail = json.loads(aj)
                    except Exception:
                        answers_detail = []

                    if answers_detail and (answered == 0 and omitted == 0):
                        answered = sum(1 for a in answers_detail if (a.get("value") or a.get("studentValue")) is not None)
                        incorrect = sum(1 for a in answers_detail
                                        if (a.get("isCorrect") is False) or (
                                            a.get("isCorrect") is None and a.get("value") and a.get("correctValue")
                                            and str(a.get("value")).upper()!=str(a.get("correctValue")).upper()))
                        correct = sum(1 for a in answers_detail
                                      if (a.get("isCorrect") is True) or (
                                          a.get("isCorrect") is None and a.get("value") and a.get("correctValue")
                                          and str(a.get("value")).upper()==str(a.get("correctValue")).upper()))
                        if answered and (correct+incorrect)==answered:
                            percent = round((correct/answered)*100, 2)

                    st.markdown(f"**{sid}**")
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("✅ Correctas", correct)
                    c2.metric("❌ Incorrectas", incorrect)
                    c3.metric("🧮 Contestadas", answered)
                    c4.metric("🕳️ Omitidas", omitted)
                    c5.metric("🎯 Acierto", f"{percent:.2f}%")

                    if answers_detail:
                        st.caption("Detalle por pregunta:")
                        show = []
                        for a in sorted(answers_detail, key=lambda x: (x.get("q") or x.get("question") or 0)):
                            q = a.get("q") or a.get("question")
                            sv = a.get("value") or a.get("studentValue")
                            cv = a.get("correctValue")
                            show.append({"Pregunta": q, "Marcó": sv, "Correcta": cv})
                        st.dataframe(pd.DataFrame(show), use_container_width=True)
                    st.markdown("---")

    with tab3:
        st.subheader("Datos filtrados")
        st.dataframe(df_filtered, use_container_width=True)

        exports = make_exports(df_filtered)

        st.markdown('<div class="toolbar">', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1,1,1,1])

        with c1:
            st.markdown('<div class="pill-btn primary">', unsafe_allow_html=True)
            st.download_button("📄 Descargar PDF", exports["pdf"][0], exports["pdf"][1], "application/pdf")
            st.markdown('</div>', unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="pill-btn">', unsafe_allow_html=True)
            st.download_button("🧾 CSV Resultados", exports["csv_results"][0], exports["csv_results"][1], "text/csv")
            st.markdown('</div>', unsafe_allow_html=True)

        with c3:
            st.markdown('<div class="pill-btn">', unsafe_allow_html=True)
            st.download_button("🧮 CSV Detalle Preguntas", exports["csv_detail"][0], exports["csv_detail"][1], "text/csv")
            st.markdown('</div>', unsafe_allow_html=True)

        with c4:
            st.markdown('<div class="pill-btn">', unsafe_allow_html=True)
            st.download_button("📊 Excel (.xlsx)", exports["xlsx"][0], exports["xlsx"][1], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
