import streamlit as st

# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="Data Quality Firewall",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ==================================================
# 2. GLOBAL DARK THEME STYLING
# ==================================================

st.markdown("""
<style>
    /* Application background */
    .stApp {
        background-color: #0E1117;
    }

    /* Main content area */
    .block-container {
        max-width: 1600px;
        padding-top: 2rem;
        padding-bottom: 2.5rem;
    }

    /* Sidebar container */
    section[data-testid="stSidebar"] {
        background-color: #111827;
        border-right: 1px solid #1F2937;
    }

    /* Sidebar typography */
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #D1D5DB;
    }

    /* Navigation item styling */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {
        border-radius: 8px;
        margin: 2px 0;
        padding: 8px 12px;
        transition: background-color 0.2s ease;
    }

    section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {
        background-color: #1F2937;
    }

    /* Active navigation item */
    section[data-testid="stSidebar"] [aria-current="page"] {
        background-color: #1E293B;
        border-left: 3px solid #3B82F6;
    }

    /* Sidebar section headers */
    section[data-testid="stSidebar"] [data-testid="stSidebarSectionHeader"] {
        color: #64748B;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.2px;
    }

    /* Global UI elements */
    div[data-testid="stMetric"] {
        background: #171B24;
        border: 1px solid #292F3B;
        border-radius: 12px;
        padding: 16px;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #292F3B;
        border-radius: 10px;
        overflow: hidden;
    }

    hr {
        border-color: #1F2937;
    }
</style>
""", unsafe_allow_html=True)


# ==================================================
# 3. PAGE DEFINITIONS
# ==================================================

overview = st.Page(
    "pages/1_overview.py",
    title="Overview",
    icon=":material/dashboard:",
    default=True
)

data_sources = st.Page(
    "pages/2_data_sources.py",
    title="Data Sources",
    icon=":material/database:"
)

rules = st.Page(
    "pages/3_checks_and_rules.py",
    title="Checks & Rules",
    icon=":material/rule:"
)

incidents = st.Page(
    "pages/4_incident.py",
    title="Incidents",
    icon=":material/warning:"
)

audit_history = st.Page(
    "pages/5_history.py",
    title="Run History",
    icon=":material/history:"
)

settings = st.Page(
    "pages/6_settings.py",
    title="Settings",
    icon=":material/settings:"
)


# ==================================================
# 4. NAVIGATION ROUTER
# ==================================================

navigation = st.navigation(
    {
        "WORKSPACE": [
            overview,
            data_sources,
            rules,
            incidents,
            audit_history
        ],
        "CONFIGURATION": [
            settings
        ]
    }
)


# ==================================================
# 5. SIDEBAR BRANDING & METADATA
# ==================================================

with st.sidebar:
    st.markdown("""
    <div style="padding: 8px 4px 16px 4px; display: flex; align-items: center; gap: 12px;">
        <div style="
            background: linear-gradient(135deg, #2563EB, #1D4ED8);
            width: 42px;
            height: 42px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        ">
            🛡️
        </div>
        <div>
            <div style="color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 0.5px;">
                DATA GUARD
            </div>
            <div style="color: #94A3B8; font-size: 9px; letter-spacing: 1.8px; margin-top: 2px;">
                QUALITY FIREWALL
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()


# ==================================================
# 6. EXECUTE PAGE ROUTER
# ==================================================

navigation.run()

with st.sidebar:
    st.divider()
    st.markdown("""
    <div style="padding: 8px 4px;">
        <div style="color: #9CA3AF; font-size: 10px; font-weight: 700; letter-spacing: 1px;">
            ENVIRONMENT
        </div>
        <div style="color: #64748B; font-size: 11px; margin-top: 4px;">
            TiDB Cloud · v1.0 MVP
        </div>
    </div>
    """, unsafe_allow_html=True)