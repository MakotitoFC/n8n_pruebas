import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
from io import BytesIO
from pathlib import Path
import json

# Ruta absoluta y estable a la BD, junto al script
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "results.db")
PDF_FILE = str(BASE_DIR / "reporte_estadisticas.pdf")

# ---------- Inicialización y migraciones ----------
def _column_exists(conn, table, col):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table});")
    cols = [r[1] for r in cur.fetchall()]
    return col in cols

def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Tabla base
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        exam_id TEXT NOT NULL,
        correct_count INTEGER DEFAULT 0,
        incorrect_count INTEGER DEFAULT 0,
        percent_correct REAL DEFAULT 0.0,
        timestamp TEXT NOT NULL
    );
    """)
    conn.commit()

    # Migraciones suaves: agregar columnas si faltan
    # answered_count, omitted_count, answers_json
    if not _column_exists(conn, "exam_results", "answered_count"):
        try:
            cur.execute("ALTER TABLE exam_results ADD COLUMN answered_count INTEGER DEFAULT 0;")
        except Exception:
            pass
    if not _column_exists(conn, "exam_results", "omitted_count"):
        try:
            cur.execute("ALTER TABLE exam_results ADD COLUMN omitted_count INTEGER DEFAULT 0;")
        except Exception:
            pass
    if not _column_exists(conn, "exam_results", "answers_json"):
        try:
            cur.execute("ALTER TABLE exam_results ADD COLUMN answers_json TEXT;")
        except Exception:
            pass

    conn.commit()
    conn.close()

# ---------- Inserta un resultado ----------
def insert_result(
    student_id: str,
    exam_id: str,
    correct: int,
    incorrect: int,
    percent: float,
    timestamp: str,
    answered_count: int = None,
    omitted_count: int = None,
    answers_json: str = None,
    db_path: str = DB_PATH
):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO exam_results
        (student_id, exam_id, correct_count, incorrect_count, percent_correct, timestamp,
         answered_count, omitted_count, answers_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        student_id, exam_id, int(correct), int(incorrect), float(percent), timestamp,
        int(answered_count or 0), int(omitted_count or 0), answers_json
    ))
    conn.commit()
    conn.close()

# ---------- Lee datos (para dashboard) ----------
def load_data(db_path: str = DB_PATH) -> pd.DataFrame:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("""
        SELECT id, student_id, exam_id, correct_count, incorrect_count, percent_correct,
               answered_count, omitted_count, answers_json, timestamp
        FROM exam_results
        ORDER BY timestamp DESC;
    """, conn)
    conn.close()
    return df

# ---------- Siguiente secuencia para student_id dentro de un exam_id ----------
def next_student_seq_for_exam(exam_id: str, db_path: str = DB_PATH) -> int:
    """
    Devuelve el siguiente N para enumerar student_id como estNN dentro de un exam_id.
    Implementación simple y robusta: COUNT(*) + 1 de las filas con ese exam_id.
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exam_results WHERE exam_id = ?", (exam_id,))
    total = cur.fetchone()[0] or 0
    conn.close()
    return int(total) + 1


# ---------- (Opcional) utilidades para PDF si las necesitas fuera del dashboard ----------
def generar_estadisticas(df: pd.DataFrame):
    return {
        "Total Registros": int(len(df)),
        "Máximo (%)": round(df["percent_correct"].max(), 2),
        "Mínimo (%)": round(df["percent_correct"].min(), 2),
    }

def graficar(df: pd.DataFrame) -> BytesIO:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].hist(df["percent_correct"], bins=10, edgecolor="black")
    axes[0].set_title("Distribución de porcentajes de aciertos")
    axes[0].set_xlabel("Porcentaje")
    axes[0].set_ylabel("Frecuencia")

    df_sorted = df.sort_values("percent_correct", ascending=False)
    axes[1].bar(df_sorted["student_id"], df_sorted["percent_correct"])
    axes[1].set_title("Ranking de desempeño por estudiante")
    axes[1].set_xlabel("Estudiante")
    axes[1].set_ylabel("Porcentaje (%)")
    axes[1].tick_params(axis='x', rotation=45)

    plt.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    buffer.seek(0)
    return buffer

def _pdf_safe(text: str) -> str:
    return ''.join(ch for ch in text if ord(ch) <= 0xFFFF and ch != '\uFE0F')

def generar_pdf(df: pd.DataFrame, stats: dict, fig_buffer: BytesIO, pdf_path: str = PDF_FILE):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _pdf_safe("Reporte de Evaluaciones"), ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Arial", "", 12)
    for k, v in stats.items():
        pdf.cell(0, 8, _pdf_safe(f"{k}: {v}"), ln=True)

    pdf.ln(10)
    pdf.image(fig_buffer, x=10, w=180, type="PNG")

    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, _pdf_safe("Resultados (resumen)"), ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", "", 10)
    for _, row in df.iterrows():
        line = f"{row['timestamp']} | {row['student_id']} | {row['exam_id']} | {row['percent_correct']}%"
        pdf.cell(0, 8, _pdf_safe(line), ln=True)

    pdf.output(pdf_path)
    print(f"✅ Reporte PDF generado: {pdf_path}")

# CLI opcional
def main():
    df = load_data()
    if df.empty:
        print("⚠️ No se encontraron registros.")
        return
    stats = generar_estadisticas(df)
    print("📈 Estadísticas:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    fig_buffer = graficar(df)
    generar_pdf(df, stats, fig_buffer)

if __name__ == "__main__":
    main()
