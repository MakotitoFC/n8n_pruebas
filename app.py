import streamlit as st
import requests
import base64

st.title("Evaluador de Exámenes con IA")

imagen = st.file_uploader("Sube una imagen del examen", type=["png", "jpg", "jpeg"])

if imagen:
    # Leer y convertir a base64
    imagen_bytes = imagen.read()
    imagen_b64 = base64.b64encode(imagen_bytes).decode()

    if st.button("Enviar a evaluación"):
        response = requests.post(
            "https://mari25.app.n8n.cloud/webhook-test/submit-exam",  # Reemplaza con tu URL real
            json={"image_base64": imagen_b64}
        )

        if response.status_code == 200:
            resultado = response.json()
            st.success("Resultados recibidos")
            st.json(resultado)
        else:
            st.error("Error al procesar la imagen.")
