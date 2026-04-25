"""Custom CSS to give the Streamlit app a polished, Transurban-like look."""

import streamlit as st


def apply_custom_css():
    st.markdown("""
    <style>
    /* Overall tightening */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #F5F4EF;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #F5F4EF;
        padding: 12px 16px;
        border-radius: 8px;
        border: 0.5px solid rgba(0,0,0,0.06);
    }
    [data-testid="stMetricLabel"] {
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #5F5E5A;
    }
    [data-testid="stMetricValue"] {
        font-size: 22px;
        font-weight: 500;
    }

    /* Headings */
    h1 { font-weight: 500; font-size: 24px; }
    h2 { font-weight: 500; font-size: 18px; }
    h3 { font-weight: 500; font-size: 15px; }

    /* Code blocks */
    code {
        background: #F1EFE8;
        padding: 1px 6px;
        border-radius: 4px;
        font-size: 0.9em;
    }

    /* Defect priority badges */
    .badge-high { color: #791F1F; background: #FCEBEB; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
    .badge-med  { color: #633806; background: #FAEEDA; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }
    .badge-low  { color: #27500A; background: #EAF3DE; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; }

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

    /* Hide the default "Made with Streamlit" footer */
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
