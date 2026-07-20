"""
app.py

Harness Streamlit per l'agente: chat + sidebar calendario.
Equivalente funzionale di ADK Web, ma esegue davvero i nostri tool.

Avvio:
    streamlit run app.py
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_calendar import calendar as calendar_widget

from agent_core import AgentCore
from tools.calendar_api import read_calendar
from tools.google_auth import accesso

# ---------------------------------------------------------------------------
# Configurazione pagina e costanti
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Assistente Mail & Calendario", page_icon="🗓️", layout="wide")

USER_AVATAR = "🧑"
BOT_AVATAR = "🗓️"
ROME_TZ = ZoneInfo("Europe/Rome")

CALENDAR_OPTIONS = {
    "editable": False,
    "selectable": False,
    "headerToolbar": {"left": "prev", "center": "title", "right": "next"},
    "footerToolbar": {"left": "today", "right": "dayGridDay,dayGridWeek,dayGridMonth"},
    "slotMinTime": "06:00:00",
    "slotMaxTime": "22:00:00",
    "initialView": "dayGridMonth",
}

CUSTOM_CSS = """
    .fc-event-past { opacity: 0.8; }
    .fc-event-time { font-style: italic; }
    .fc-event-title { font-weight: 700; }
    .fc-toolbar-title { font-size: 1.6rem; }
"""


# ---------------------------------------------------------------------------
# Inizializzazione dello stato (una sola volta per sessione)
# ---------------------------------------------------------------------------
def init_state() -> None:
    if "agent" not in st.session_state:
        st.session_state.agent = AgentCore()
    if "history" not in st.session_state:
        st.session_state.history = []
    if "display_messages" not in st.session_state:
        st.session_state.display_messages = []
    if "calendar_dirty" not in st.session_state:
        st.session_state.calendar_dirty = True
    if "cal_events" not in st.session_state:
        st.session_state.cal_events = []
    # Richiesta utente in attesa di essere processata al prossimo rerun.
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None


# ---------------------------------------------------------------------------
# Caricamento eventi calendario per la sidebar
# ---------------------------------------------------------------------------
def load_calendar_events(days_back: int = 15, days_fwd: int = 45) -> list:
    """Legge gli eventi reali da Google Calendar per la sidebar."""
    try:
        creds = accesso()
        today = datetime.datetime.now(ROME_TZ)
        date_info = {
            "start": (today - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d"),
            "end": (today + datetime.timedelta(days=days_fwd)).strftime("%Y-%m-%d"),
        }
        raw_events = read_calendar(creds, date_info)

        events = []
        for e in raw_events:
            start = e["start"].get("dateTime", e["start"].get("date"))
            end = e["end"].get("dateTime", e["end"].get("date"))
            events.append(
                {"title": e.get("summary", "Senza titolo"), "start": start, "end": end}
            )
        return events
    except Exception as exc:  # noqa: BLE001
        st.sidebar.warning(f"Impossibile caricare il calendario: {exc}")
        return []


# ---------------------------------------------------------------------------
# UI - rendering (nessun lavoro pesante qui dentro)
# ---------------------------------------------------------------------------
def render_header() -> None:
    st.markdown(
        "<h1 style='text-align:center;'>Assistente Mail & Calendario</h1>",
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        st.link_button("📧 Gmail", "https://mail.google.com", use_container_width=True)
    with col2:
        st.link_button("📆 Calendar", "https://calendar.google.com", use_container_width=True)


def render_chat_history() -> None:
    """Unico punto in cui i messaggi vengono disegnati."""
    for msg in st.session_state.display_messages:
        with st.chat_message(msg["role"], avatar=msg.get("avatar")):
            st.markdown(msg["content"])


def render_sidebar() -> None:
    with st.sidebar:
        st.subheader("Il tuo calendario")
        if st.button("🔄 Aggiorna", use_container_width=True):
            st.session_state.calendar_dirty = True

        if st.session_state.calendar_dirty:
            st.session_state.cal_events = load_calendar_events()
            st.session_state.calendar_dirty = False

        calendar_widget(
            events=st.session_state.cal_events,
            options=CALENDAR_OPTIONS,
            custom_css=CUSTOM_CSS,
            key="calendar",
        )


# ---------------------------------------------------------------------------
# Elaborazione della richiesta (lavoro pesante, fuori dai context manager UI)
# ---------------------------------------------------------------------------
def process_pending_prompt() -> None:
    """
    Esegue il turno agentico per la richiesta in sospeso.
    Aggiorna SOLO lo stato: il disegno avviene in render_chat_history al rerun.
    """
    prompt = st.session_state.pending_prompt
    if not prompt:
        return

    with st.spinner("Sto elaborando la richiesta..."):
        agent = st.session_state.agent
        agent.on_tool_call = lambda name, args: None  # log gestito nel core
        try:
            result = agent.run_turn(st.session_state.history, prompt)
            answer = result.text
            calendar_changed = result.calendar_changed
            st.session_state.history = result.messages
        except Exception as exc:  # noqa: BLE001
            answer = f"Si e' verificato un errore: {exc}"
            calendar_changed = False

    st.session_state.display_messages.append(
        {"role": "assistant", "avatar": BOT_AVATAR, "content": answer}
    )
    st.session_state.pending_prompt = None
    if calendar_changed:
        st.session_state.calendar_dirty = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    init_state()
    render_header()

    # 1. Se c'e' una richiesta in sospeso, elaborala PRIMA di disegnare la chat.
    if st.session_state.pending_prompt:
        process_pending_prompt()

    # 2. Disegna la cronologia (punto unico di rendering dei messaggi).
    render_chat_history()

    # 3. Sidebar calendario.
    render_sidebar()

    # 4. Input utente: registra il messaggio e richiede un rerun.
    if prompt := st.chat_input("Scrivi una richiesta su mail o calendario..."):
        st.session_state.display_messages.append(
            {"role": "user", "avatar": USER_AVATAR, "content": prompt}
        )
        st.session_state.pending_prompt = prompt
        st.rerun()


if __name__ == "__main__":
    main()