"""Custom CSS to give the Streamlit app a polished, Transurban-like look."""

import streamlit as st


def apply_custom_css():
    st.markdown("""
    <style>
    /* App scale */
    html, body, .stApp {
        font-size: 18px !important;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
    }

    .stApp {
        color: #1F2328;
        background: #FBFAF6;
    }

    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 2.5rem;
        max-width: 1500px;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #F5F4EF;
    }
    [data-testid="stSidebar"] * {
        font-size: 17px !important;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #F5F4EF;
        padding: 22px 24px;
        border-radius: 8px;
        border: 1px solid rgba(0,0,0,0.08);
    }
    [data-testid="stMetricLabel"] {
        min-height: 2.4rem;
        font-size: 15px !important;
        text-transform: uppercase;
        letter-spacing: 0;
        color: #5F5E5A;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.2 !important;
    }
    [data-testid="stMetricLabel"] * {
        font-size: 15px !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.2 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 42px !important;
        font-weight: 700 !important;
        color: #171A1F !important;
        line-height: 1.05 !important;
    }
    [data-testid="stMetricValue"] * {
        font-size: 42px !important;
        font-weight: 700 !important;
    }

    /* Headings */
    h1,
    [data-testid="stMarkdownContainer"] h1 {
        font-weight: 700 !important;
        font-size: 48px !important;
        line-height: 1.12 !important;
    }
    h2,
    [data-testid="stMarkdownContainer"] h2 {
        font-weight: 700 !important;
        font-size: 34px !important;
        line-height: 1.18 !important;
    }
    h3,
    [data-testid="stMarkdownContainer"] h3 {
        font-weight: 700 !important;
        font-size: 26px !important;
        line-height: 1.22 !important;
    }
    p, li, label,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] *,
    [data-testid="stAlert"] *,
    .stMarkdown {
        font-size: 18px !important;
        line-height: 1.55 !important;
    }

    /* Inputs and selections */
    [data-testid="stWidgetLabel"] *,
    [data-baseweb="select"] > div,
    [data-baseweb="select"] *,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploader"] *,
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] label *,
    [data-testid="stCheckbox"] label,
    [data-testid="stCheckbox"] label *,
    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button {
        font-size: 18px !important;
        color: #1F2328 !important;
    }
    [data-baseweb="select"] > div {
        min-height: 54px !important;
        border-color: #B9B5A8 !important;
        background: #FFFFFF !important;
        box-shadow: none !important;
    }
    [data-baseweb="select"] input {
        font-size: 18px !important;
    }
    [data-baseweb="popover"] *,
    [data-baseweb="popover"] [role="option"],
    [data-baseweb="popover"] li {
        font-size: 18px !important;
        color: #1F2328 !important;
        filter: none !important;
        text-shadow: none !important;
        opacity: 1 !important;
    }
    [data-baseweb="tag"] {
        min-height: 36px !important;
        border-radius: 6px;
        background: #E9F0EC !important;
        color: #143C2C !important;
    }
    [data-baseweb="tag"] span {
        font-size: 17px !important;
        font-weight: 600;
    }
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        min-height: 40px !important;
        align-items: center;
    }
    [data-testid="stButton"] button,
    [data-testid="stDownloadButton"] button {
        min-height: 48px !important;
        padding: 0.6rem 1rem !important;
    }

    /* Code blocks */
    code {
        background: #F1EFE8;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 1em !important;
    }

    /* Defect priority badges */
    .badge-high { color: #791F1F; background: #FCEBEB; padding: 6px 12px; border-radius: 12px; font-size: 16px; font-weight: 700; }
    .badge-med  { color: #633806; background: #FAEEDA; padding: 6px 12px; border-radius: 12px; font-size: 16px; font-weight: 700; }
    .badge-low  { color: #27500A; background: #EAF3DE; padding: 6px 12px; border-radius: 12px; font-size: 16px; font-weight: 700; }

    /* Progress bars for completeness */
    .completeness-bar {
        height: 6px;
        background: #E5E4DE;
        border-radius: 3px;
        overflow: hidden;
    }
    .completeness-fill { height: 100%; border-radius: 3px; }
    .fill-high   { background: #1D9E75; }
    .fill-med    { background: #BA7517; }
    .fill-low    { background: #E24B4A; }

    /* Tables and editable grids */
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"] {
        font-size: 18px !important;
    }
    [data-testid="stDataFrame"] canvas,
    [data-testid="stDataEditor"] canvas {
        image-rendering: auto;
    }
    [data-testid="stDataFrame"] [role="gridcell"],
    [data-testid="stDataEditor"] [role="gridcell"],
    [data-testid="stDataFrame"] [role="columnheader"],
    [data-testid="stDataEditor"] [role="columnheader"] {
        font-size: 15px !important;
        color: #1F2328 !important;
    }

    /* Hide the default "Made with Streamlit" footer */
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
