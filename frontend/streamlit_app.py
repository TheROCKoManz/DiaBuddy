import requests
import streamlit as st

# FastAPI is reachable internally at :8000 (same container, bypasses nginx)
API_BASE = "http://localhost:8000"

st.set_page_config(page_title="DiaBuddy", page_icon="💉", layout="centered")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_token(token: str) -> str | None:
    """Calls /api/me to verify the JWT and return the user's email, or None if invalid."""
    try:
        r = requests.get(
            f"{API_BASE}/api/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("email")
    except requests.RequestException:
        pass
    return None


# ---------------------------------------------------------------------------
# Token bootstrap — pick up JWT from OAuth redirect query param
# ---------------------------------------------------------------------------

if "token" not in st.session_state:
    token_param = st.query_params.get("token")
    if token_param:
        email = validate_token(token_param)
        if email:
            st.session_state.token = token_param
            st.session_state.email = email
            st.query_params.clear()   # clean the URL
            st.rerun()


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------

if "token" not in st.session_state:
    st.title("DiaBuddy")
    st.subheader("Insulin Dosage Assistant")
    st.write("Estimate your Apidra insulin dose before a meal — powered by AI.")
    st.markdown("---")
    st.markdown(
        '<a href="/auth/google" target="_self" style="display:block;text-align:center;'
        'padding:0.5rem 1rem;background:#4285F4;color:white;border-radius:4px;'
        'text-decoration:none;font-weight:500;">Sign in with Google</a>',
        unsafe_allow_html=True,
    )
    st.caption("Only authorized Google accounts can access this app.")
    st.stop()


# ---------------------------------------------------------------------------
# Main app (authenticated)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f"**Signed in as**  \n{st.session_state.email}")
    st.markdown("---")
    if st.button("Sign out", use_container_width=True):
        del st.session_state.token
        del st.session_state.email
        st.rerun()

st.title("DiaBuddy 💉")
st.write("Describe everything you're about to eat and your current blood sugar to get your Apidra dose.")
st.markdown("---")

meal_description = st.text_area(
    "What are you eating?",
    placeholder="e.g. 3 slices of medium pepperoni pizza. 1 glass of coke, 30 ml baileys ice cream",
    height=100,
)
blood_sugar = st.number_input(
    "Pre-meal blood sugar (mg/dl)",
    min_value=40,
    max_value=500,
    value=120,
    step=1,
)

if st.button("Calculate Insulin Dose", type="primary", use_container_width=True):
    if not meal_description.strip():
        st.warning("Please describe what you're eating.")
    else:
        with st.spinner("Researching your food and calculating dose — this may take a moment..."):
            try:
                response = requests.post(
                    f"{API_BASE}/api/check-insulin",
                    json={"meal_description": meal_description, "blood_sugar": blood_sugar},
                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                    timeout=180,
                )
            except requests.RequestException as e:
                st.error(f"Could not reach the backend: {e}")
                st.stop()

        if response.status_code == 401:
            st.error("Your session has expired. Please sign in again.")
            del st.session_state.token
            del st.session_state.email
            st.rerun()
        elif response.status_code == 200:
            result = response.json()
            st.success("Dosage calculated")
            st.markdown(f"### Recommendation\n\n{result['recommendation']}")
        else:
            try:
                detail = response.json().get("detail", "Unknown error")
            except Exception:
                detail = response.text or f"HTTP {response.status_code}"
            st.error(f"Error: {detail}")

st.markdown("---")
st.caption(
    "⚠️ This tool provides AI estimations only. "
    "Always consult your endocrinologist before adjusting your insulin dose."
)