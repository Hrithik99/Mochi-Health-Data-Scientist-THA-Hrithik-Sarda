"""
Mood Tracker – Mochi Health take‑home
====================================
Lightweight Streamlit app to record the mood of each support ticket and
show a live bar chart for the current day. Storage is a shared Google
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
    from streamlit_extras.st_autorefresh import st_autorefresh  # type: ignore
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

# 2 · Google Sheets client

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

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_df() -> pd.DataFrame:
    rows = ws.get_all_values()[1:]
    if not rows:
        return pd.DataFrame(columns=["timestamp", "mood", "note"])
    df = pd.DataFrame(rows, columns=["timestamp", "mood", "note"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True).dt.tz_convert("America/New_York")
    return df

def filter_df_by_day(df: pd.DataFrame, selected_date: dt.date) -> pd.DataFrame:
    if df.empty:
        return df
    day_start = pd.Timestamp(selected_date, tz="America/New_York")
    day_end = day_start + pd.Timedelta(days=1)
    return df[(df["timestamp"] >= day_start) & (df["timestamp"] < day_end)]

def filter_df_by_range(df: pd.DataFrame, start_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    if df.empty:
        return df
    start = pd.Timestamp(start_date, tz="America/New_York")
    end = pd.Timestamp(end_date, tz="America/New_York") + pd.Timedelta(days=1)
    return df[(df["timestamp"] >= start) & (df["timestamp"] < end)]

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

st.sidebar.markdown(
    """
    <div style="font-size:0.95em; color: #666; margin-bottom:0.2em;">
        <b>Mood legend</b>
    </div>
    <div style="font-size:0.85em; color: #888; line-height:1.1; margin-bottom:0.8em;">
        {}
    </div>
    """.format(
        "<br>".join(f"<span>{emoji}</span> — <span>{desc}</span>" for emoji, desc in MOODS)
    ),
    unsafe_allow_html=True,
)

# --- Date/range filter UI starts here ---
st.sidebar.markdown("---")

df_all = fetch_all_df()

date_mode = st.sidebar.radio(
    "View by", ["Single day", "Date range", "All data"], horizontal=True
)

min_date = df_all["timestamp"].min().date() if not df_all.empty else pd.Timestamp.now().date()
max_date = df_all["timestamp"].max().date() if not df_all.empty else pd.Timestamp.now().date()

if date_mode == "Single day":
    selected_date = st.sidebar.date_input(
        "Choose day",
        value=max_date,
        min_value=min_date,
        max_value=max_date,
        key="single_date"
    )
    df_filtered = filter_df_by_day(df_all, selected_date)

elif date_mode == "Date range":
    range_val = st.sidebar.date_input(
        "Pick date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="range_date"
    )

    # Defensive handling for all possible user interactions:
    if isinstance(range_val, tuple):
        if len(range_val) == 2:
            start_date, end_date = range_val
        elif len(range_val) == 1:
            start_date = end_date = range_val[0]
        else:
            # Fallback: unexpected tuple length, use full range
            start_date, end_date = min_date, max_date
    else:
        start_date = end_date = range_val  # single date

    if start_date > end_date:
        st.sidebar.warning("Start date must be before end date.")
        df_filtered = df_all.iloc[0:0]  # empty
    else:
        df_filtered = filter_df_by_range(df_all, start_date, end_date)

else:  # "All data"
    df_filtered = df_all

# --- End of new filter section ---

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
        st.cache_data.clear()  # <-- This line clears the cache immediately!
        st.sidebar.success("Logged!")
        # reset mood + note for next entry on the *next* run
        st.session_state.selected_mood = None
        st.session_state._clear_note = True
        _rerun()


# --- Chart display section with dynamic titles ---
if df_filtered.empty:
    st.info("No moods logged for the selected period yet.")
else:
    counts = (
        df_filtered.groupby("mood").size()
        .reindex([e for e, _ in MOODS], fill_value=0)
        .reset_index(name="count")
    )

    # Dynamic chart title
    if date_mode == "Single day":
        title = f"Mood distribution for {selected_date.strftime('%A, %B %d, %Y')}"
    elif date_mode == "Date range":
        title = f"Moods from {start_date.strftime('%b %d, %Y')} to {end_date.strftime('%b %d, %Y')}"
    else:
        title = "Mood distribution (All data)"

    fig = px.bar(
        counts,
        x="mood",
        y="count",
        text="count",
        title=title,
    )
    fig.update_layout(
        yaxis_title="Tickets",
        xaxis_title="Mood",
        showlegend=False,
        xaxis_tickfont=dict(size=30),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# Auto‑refresh (every 30 s) if package available
st_autorefresh(interval=9000, key="autorefresh")

# UI polish: show last updated
st.sidebar.caption(f"Last refresh: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
