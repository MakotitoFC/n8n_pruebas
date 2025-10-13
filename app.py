import streamlit as st
import requests
import json

# --- CONFIGURACIÓN ---
N8N_WEBHOOK_URL = "https://aldosanchez.app.n8n.cloud/webhook-test/exam-auto-grader"

st.set_page_config(page_title="AutoGrader", page_icon="✅", layout="centered")

st.title("📘 Evaluador Automático de Exámenes")
st.write("Sube la hoja de respuestas y la plantilla para obtener la calificación.")

# --- FORMULARIO DE ENTRADA ---
student_id = st.text_input("ID del Estudiante", value="123")
exam_id = st.text_input("ID del Examen", value="mat101")

st.markdown("### 🧾 Plantilla de respuestas correctas (JSON)")
answer_key_text = st.text_area(
    "Ejemplo: {'1':'A','2':'C','3':'V'}",
    value='{"1":"A","2":"C","3":"V"}',
    height=100
)

uploaded_file = st.file_uploader(
    "📸 Sube la imagen del examen (foto o escaneo)",
    type=["jpg", "jpeg", "png"]
)

def safe_parse_answer_key(txt: str):
    try:
        return json.loads(txt)
    except Exception:
        return None

# --- ENVÍO ---
if st.button("Enviar para corrección", use_container_width=True):
    if uploaded_file is None:
        st.warning("⚠️ Debes subir una imagen primero.")
    else:
        # Validar JSON de la clave
        answer_key_obj = safe_parse_answer_key(answer_key_text)
        if answer_key_obj is None:
            st.error("❌ La plantilla (answer_key) no es JSON válido. Corrígela e inténtalo de nuevo.")
        else:
            try:
                st.info("⏳ Procesando la imagen, por favor espera...")

                # Preparar multipart/form-data
                file_bytes = uploaded_file.getvalue()
                files = {
                    'exam_image': (
                        uploaded_file.name,
                        file_bytes,
                        uploaded_file.type or "application/octet-stream"
                    )
                }
                # Envía answer_key como string JSON
                data = {
                    'student_id': student_id,
                    'exam_id': exam_id,
                    'answer_key': json.dumps(answer_key_obj)
                }

                # Enviar a n8n Webhook
                response = requests.post(N8N_WEBHOOK_URL, data=data, files=files, timeout=60)

                if response.status_code == 200:
                    # La respuesta del nodo "Respond to Webhook"
                    # debería ser JSON (desde ScoreCalculator)
                    result = response.json()
                    st.success("✅ Resultados recibidos correctamente")

                    st.write("### 📊 Resumen del examen")
                    st.json(result)

                    # Nombres estándar según el ScoreCalculator de ejemplo
                    total = result.get("total_questions")
                    correct = result.get("correct_answers")
                    score = result.get("score")  # 0-100 en el ejemplo

                    # Fallbacks si n8n devolviera otros nombres
                    if total is None and "answers" in result:
                        total = len(result["answers"])
                    if correct is None and "correct_count" in result:
                        correct = result["correct_count"]
                    incorrect = None
                    if total is not None and correct is not None:
                        try:
                            incorrect = int(total) - int(correct)
                        except Exception:
                            pass
                    percent = score
                    if percent is None and total and correct is not None:
                        try:
                            percent = round((int(correct) / int(total)) * 100, 2)
                        except Exception:
                            pass

                    # Métricas
                    if correct is not None:
                        st.metric("Respuestas Correctas", correct)
                    if incorrect is not None:
                        st.metric("Respuestas Incorrectas", incorrect)
                    if percent is not None:
                        st.metric("Porcentaje de aciertos", f"{percent}%")

                    # Detalle por pregunta (si viene)
                    # Si solo vienen respuestas, las listamos; si viene answer_key, mostramos correcto/incorrecto.
                    st.write("### Detalle por pregunta:")
                    answers = result.get("answers", [])
                    answer_key = result.get("answer_key", answer_key_obj)

                    if answers:
                        for a in answers:
                            # soporta dos formatos: {q, value} ó {question, studentValue, correctValue, isCorrect}
                            q = a.get("q") or a.get("question")
                            student_val = a.get("value") or a.get("studentValue")
                            correct_val = a.get("correctValue") or (answer_key.get(str(q)) if q is not None else None)
                            is_correct = a.get("isCorrect")
                            if is_correct is None and (student_val is not None and correct_val is not None):
                                is_correct = str(student_val).upper() == str(correct_val).upper()
                            icon = "✅" if is_correct else "❌"
                            if q is not None:
                                st.write(f"{icon} Pregunta {q}: Marcó {student_val} / Correcta {correct_val}")
                            else:
                                st.write(f"- Respuesta: {student_val}")

                else:
                    st.error(f"❌ Error {response.status_code}: {response.text}")

            except Exception as e:
                st.error(f"Error al comunicarse con n8n: {e}")
