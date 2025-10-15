# styles.py
import streamlit as st

TOKENS = {
    "PRIMARY": "#0D47A1",
    "PRIMARY_SOFT": "#E3F2FD",
    "PRIMARY_MID": "#1976D2",
    "BG_GRAD_TOP": "#F5FAFF",
    "BG_GRAD_BOT": "#FFFFFF",
    "SIDEBAR_BG": "#F0F6FF",
    "CARD_BORDER": "#E6EEF8",
}

def build_css(t=TOKENS) -> str:
    return f"""
/* Fondo general */
.stApp {{
  background: linear-gradient(180deg, {t['BG_GRAD_TOP']} 0%, {t['BG_GRAD_BOT']} 60%);
  color: #1f2937;
  font-family: "Inter", system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}}

/* --- LOGIN centrado --- */
.login-wrap {{
  min-height: 92vh; display:flex; align-items:center; justify-content:center;
  background: radial-gradient(1000px 360px at 50% 0%, {t['PRIMARY_SOFT']}, transparent);
}}
.login-card {{
  width: min(860px, 92vw);
  background: #fff;
  border: 1px solid {t['CARD_BORDER']};
  border-radius: 18px;
  padding: 24px;
  box-shadow: 0 18px 60px rgba(13,71,161,.18);
}}
.login-header {{
  background: linear-gradient(90deg, {t['PRIMARY']} 0%, {t['PRIMARY_MID']} 60%);
  color:#fff; padding: 18px 20px; border-radius: 14px; margin-bottom: 14px;
}}
.login-header h2 {{ margin:0; font-size:26px; font-weight:800; }}
.login-header p {{ margin:6px 0 0 0; opacity:.95; }}

/* --- Encabezado principal --- */
.header-box {{
  background: linear-gradient(90deg, {t['PRIMARY']} 0%, {t['PRIMARY_MID']} 60%);
  color: white; padding: 22px 26px; border-radius: 18px;
  box-shadow: 0 14px 36px rgba(13,71,161,.25); margin: 8px 0 18px 0;
}}
.header-box h1 {{ font-size: 28px; margin: 0; font-weight: 800; }}
.header-box p {{ opacity: .95; margin: 8px 0 0 0; }}

/* --- Sidebar / Filtros --- */
[data-testid="stSidebar"] {{
  background: {t['SIDEBAR_BG']};
  border-right: 1px solid {t['CARD_BORDER']};
}}
.sidebar-title {{
  display:flex;align-items:center;gap:.5rem;
  color:{t['PRIMARY']};font-weight:800;letter-spacing:.3px;margin:6px 0 10px 2px;
}}
.sidebar-card {{
  background: #fff;
  border: 1px solid {t['CARD_BORDER']};
  border-radius: 16px;
  padding: 14px 12px 14px 12px;
  box-shadow: 0 6px 18px rgba(13,71,161,.06);
}}

/* --- Botones --- */
.stButton > button[kind="primary"] {{
  background: {t['PRIMARY_MID']}; border: 1px solid {t['PRIMARY_MID']};
  color: #fff !important; font-weight: 800; border-radius: 12px;
  box-shadow: 0 6px 18px rgba(25,118,210,.25);
}}
.stButton > button[kind="primary"]:hover {{
  background: {t['PRIMARY']}; border-color: {t['PRIMARY']};
}}
/* Fuerza color blanco tambiÃ©n en el emoji/Ã­cono del label */
.stButton > button span {{ color: #fff !important; }}

/* --- KPIs / Cards --- */
.kpi {{
  background: white; border-radius: 14px; border: 1px solid {t['CARD_BORDER']};
  padding: 16px; box-shadow: 0 4px 14px rgba(13,71,161,.08);
}}
.kpi h4 {{ color: #2c3e50; font-weight: 600; margin: 0 0 6px 0; font-size: 13px; }}
.kpi .val {{ color: {t['PRIMARY']}; font-size: 24px; font-weight: 800; }}

/* --- Tabs --- */
.stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
.stTabs [data-baseweb="tab"] {{
  background: #fff; border: 1px solid {t['CARD_BORDER']}; color: #0f172a;
  padding: 10px 14px; border-radius: 12px; box-shadow: 0 3px 10px rgba(13,71,161,.06);
}}
.stTabs [aria-selected="true"] {{
  background: {t['PRIMARY_SOFT']}; color: {t['PRIMARY']}; border-color: {t['PRIMARY_MID']};
}}

/* --- Inputs --- */
.stTextInput > div > div > input, .stTextArea textarea, .stSelectbox > div > div {{
  border-radius: 10px !important; border: 1px solid {t['CARD_BORDER']} !important;
  background: #fff !important;
}}

/* --- Export buttons --- */
.toolbar {{ display:flex; gap:12px; flex-wrap:wrap; }}
.pill-btn > button {{
  border-radius: 999px !important; padding: 10px 16px !important; font-weight: 700 !important;
  border: 1px solid {t['PRIMARY_MID']} !important; color: {t['PRIMARY']} !important; background:#fff !important;
}}
.pill-btn > button:hover {{
  background: {t['PRIMARY_SOFT']} !important; color: {t['PRIMARY']} !important;
}}
.pill-btn.primary > button {{ background: {t['PRIMARY_MID']} !important; color:#fff !important; }}
.pill-btn.primary > button:hover {{ background: {t['PRIMARY']} !important; }}
"""

def apply_css(tokens: dict | None = None):
    st.markdown(f"<style>{build_css(tokens or TOKENS)}</style>", unsafe_allow_html=True)