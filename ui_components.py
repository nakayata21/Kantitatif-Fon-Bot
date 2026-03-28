
import streamlit as st

def inject_custom_css():
    st.markdown("""
    <style>
    /* Metric Cards (Kutucuklar) */
    div[data-testid="metric-container"] {
        background-color: #1a1c24;
        border: 1px solid #2d303e;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
        border-color: #3b82f6;
    }
    /* Metric Yazıları */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700;
        color: #f3f4f6;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.95rem;
        color: #9ca3af;
        font-weight: 500;
        margin-bottom: 0.25rem;
    }
    /* Gradient Buton Tasarımı */
    .stButton>button {
        background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
        border: none;
    }
    /* Tab Menüleri */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e212b;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        color: #d1d5db;
        border: 1px solid #374151;
        border-bottom: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: white !important;
        border-color: #2563eb !important;
    }
    /* Başlık */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #60a5fa, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0rem;
    }
    /* Sidebar Header */
    [data-testid="stSidebar"] {
        background-color: #0f111a;
        border-right: 1px solid #1f2335;
    }
    /* Pulse Animasyonu */
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; transform: scale(1.02); }
        100% { opacity: 1; }
    }
    </style>
    """, unsafe_allow_html=True)

def signal_style(v: str) -> str:
    if v == "AL":
        return "background-color:#dcfce7;color:#166534;font-weight:700;"
    if v == "BEKLE":
        return "background-color:#fef3c7;color:#92400e;font-weight:700;"
    return "background-color:#fee2e2;color:#991b1b;font-weight:700;"

def action_style(v: str) -> str:
    if "🎯" in v or "SNIPER" in v or "ALPHA" in v:
        return "background-color:#fef9c3;color:#854d0e;border:2px solid #eab308;font-weight:900;animation: pulse 2s infinite;"
    if "AL" in v:
        return "background-color:#dcfce7;color:#166534;font-weight:700;"
    elif "ŞORT" in v or "SAT" in v:
        return "background-color:#fee2e2;color:#991b1b;font-weight:700;"
    return "background-color:#fef3c7;color:#92400e;font-weight:700;"
