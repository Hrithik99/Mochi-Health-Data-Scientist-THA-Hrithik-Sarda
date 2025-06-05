"""
Mood Tracker – Mochi Health take‑home
====================================
Lightweight Streamlit app to record the mood of each support ticket and
show a live bar chart for the current day.  Storage is a shared Google
Sheet so anyone on the team can peek at the raw data.
"""

from __future__ import annotations
import os, json, datetime as dt
import pandas as pd
import streamlit as st
import plotly.express as px
import gspread


# 1 · Config helpers


try:  # load .env for local runs
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:  # optional auto‑refresh 
    from streamlit_autorefresh import st_autorefresh
    #print("No autorefresh error")  # type: ignore
except ModuleNotFoundError:
    def st_autorefresh(*_, **__):
        return

MOODS: list[tuple[str, str]] = [
    ("😄", "Delighted"),
    ("🙂", "Satisfied"),
    ("😐", "Neutral"),
    ("😕", "Frustrated"),
    ("😠", "Angry"),
]
MOOD_DESC = {e: d for e, d in MOODS}


# 2 · Google Sheets client


def get_gspread_client() -> gspread.client.Client:
    if os.getenv("GOOGLE_SERVICE_ACCOUNT"):
        return gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"]))
    return gspread.service_account(filename="service_account.json")

GC = get_gspread_client()
SHEET_KEY = os.getenv("SHEET_KEY", "")
if not SHEET_KEY:
    st.error("SHEET_KEY env var missing – set it in .env or Streamlit secrets.")
    st.stop()

ws = GC.open_by_key(SHEET_KEY).sheet1  # first sheet


# 3 · Data helpers


def fetch_today_df() -> pd.DataFrame:
    rows = ws.get_all_values()[1:]
    if not rows:
        return pd.DataFrame(columns=["timestamp", "mood", "note"])
    df = pd.DataFrame(rows, columns=["timestamp", "mood", "note"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True).dt.tz_convert("America/New_York")
    today = pd.Timestamp.now(tz="America/New_York").normalize()
    tomorrow = today + pd.Timedelta(days=1)
    return df[(df["timestamp"] >= today) & (df["timestamp"] < tomorrow)]

def append_row(mood: str, note: str) -> None:
    ws.append_row([dt.datetime.now(dt.timezone.utc).isoformat(), mood, note])

def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


# 4 · Streamlit UI setup


st.set_page_config("Mood of the Queue", "📊", layout="centered")


bg_css = """
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}
[data-testid="stSidebar"] {
    background: #ffffffcc;  /* semi‑transparent white */
}
</style>
"""
st.markdown(bg_css, unsafe_allow_html=True)

st.title("📊 Mood of the Queue")


if "selected_mood" not in st.session_state:
    st.session_state.selected_mood = None
if "note_input" not in st.session_state:
    st.session_state.note_input = ""
if st.session_state.get("_clear_note", False):
    st.session_state.note_input = ""
    st.session_state._clear_note = False



st.sidebar.header("Log a ticket’s mood")

st.sidebar.markdown("### Mood legend")
for emoji, desc in MOODS:
    st.sidebar.write(f"{emoji} — {desc}")

st.sidebar.markdown("---")

cols = st.sidebar.columns(len(MOODS))
for i, (emoji, _) in enumerate(MOODS):
    if cols[i].button(emoji):
        st.session_state.selected_mood = emoji

mood = st.session_state.selected_mood
sel_text = MOOD_DESC.get(mood, "_None selected_")

st.sidebar.write("**Current selection:**", f"{mood or ''} {sel_text}")

note = st.sidebar.text_input("Optional note (120 chars max)", key="note_input")[:120]

if st.sidebar.button("Submit"):
    if mood is None:
        st.sidebar.warning("Please pick a mood first.")
    else:
        append_row(mood, note.strip())
        st.sidebar.success("Logged!")
        # reset mood + note for next entry on the *next* run
        st.session_state.selected_mood = None
        st.session_state._clear_note = True
        _rerun()



df_today = fetch_today_df()

if df_today.empty:
    st.info("No moods logged today yet. Use the sidebar to add the first entry.")
else:
    counts = (
        df_today.groupby("mood").size()
        .reindex([e for e, _ in MOODS], fill_value=0)
        .reset_index(name="count")
    )
    fig = px.bar(counts, x="mood", y="count", text="count", title="Today’s mood distribution")
    fig.update_layout(
        yaxis_title="Tickets",
        xaxis_title="Mood",
        showlegend=False,
        xaxis_tickfont=dict(size=30),  # larger emoji labels
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# Auto‑refresh (every 9 s) if package available
st_autorefresh(interval=9000, key="autorefresh")
