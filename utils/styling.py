"""Custom CSS to give the Streamlit app a polished, Transurban-like look."""

import streamlit as st


def apply_custom_css():
    st.markdown("""
    <style>
    /* App scale */
    html, body, [class*="css"] {
        font-size: 16px;
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
        max-width: 1440px;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #F5F4EF;
    }
    [data-testid="stSidebar"] * {
        font-size: 15px;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #F5F4EF;
        padding: 18px 20px;
        border-radius: 8px;
        border: 1px solid rgba(0,0,0,0.08);
    }
    [data-testid="stMetricLabel"] {
        font-size: 13px !important;
        text-transform: uppercase;
        letter-spacing: 0;
        color: #5F5E5A;
    }
    [data-testid="stMetricValue"] {
        font-size: 32px;
        font-weight: 650;
        color: #171A1F;
    }

    /* Headings */
    h1 { font-weight: 650; font-size: 36px; line-height: 1.15; }
    h2 { font-weight: 650; font-size: 26px; line-height: 1.2; }
    h3 { font-weight: 650; font-size: 20px; line-height: 1.25; }
    p, li, label, .stMarkdown, .stCaption {
        font-size: 16px;
        line-height: 1.5;
    }

    /* Inputs and selections */
    [data-baseweb="select"] > div,
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stFileUploader"] section,
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        font-size: 16px !important;
        color: #1F2328 !important;
    }
    [data-baseweb="select"] > div {
        min-height: 44px;
        border-color: #B9B5A8 !important;
        background: #FFFFFF !important;
        box-shadow: none !important;
    }
    [data-baseweb="select"] span,
    [data-baseweb="popover"] [role="option"],
    [data-baseweb="popover"] li {
        font-size: 16px !important;
        color: #1F2328 !important;
        filter: none !important;
        text-shadow: none !important;
        opacity: 1 !important;
    }
    [data-baseweb="tag"] {
        min-height: 30px;
        border-radius: 6px;
        background: #E9F0EC !important;
        color: #143C2C !important;
    }
    [data-baseweb="tag"] span {
        font-size: 15px !important;
        font-weight: 600;
    }
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        min-height: 32px;
        align-items: center;
    }

    /* Code blocks */
    code {
        background: #F1EFE8;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.95em;
    }

    /* Defect priority badges */
    .badge-high { color: #791F1F; background: #FCEBEB; padding: 4px 10px; border-radius: 12px; font-size: 13px; font-weight: 650; }
    .badge-med  { color: #633806; background: #FAEEDA; padding: 4px 10px; border-radius: 12px; font-size: 13px; font-weight: 650; }
    .badge-low  { color: #27500A; background: #EAF3DE; padding: 4px 10px; border-radius: 12px; font-size: 13px; font-weight: 650; }

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
        font-size: 15px;
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
