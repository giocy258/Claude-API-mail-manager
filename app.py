"""
app.py

Harness Streamlit per l'agente: chat + sidebar calendario.
Equivalente funzionale di ADK Web, ma esegue davvero i nostri tool.

Avvio:
    streamlit run app.py

Struttura attesa (app.py e' nella root del progetto):
    project/
    ├── app.py              <-- questo file
    ├── agent_core.py
    ├── system_prompt.md
    └── tools/
        ├── __init__.py
        ├── google_auth.py  (+ credentials.json, token.json)
        ├── ...
        └── registry.py
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_calendar import calendar

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
        # L'agente e' pesante da costruire (legge system_prompt, valida i tool):
        # lo creiamo una volta e lo teniamo nella sessione.
        st.session_state.agent = AgentCore()

    if "history" not in st.session_state:
        # History nel formato nativo Anthropic (include blocchi tool_use/tool_result).
        st.session_state.history = []

    if "display_messages" not in st.session_state:
        # Solo i messaggi testuali da mostrare in chat.
        st.session_state.display_messages = []

    if "calendar_dirty" not in st.session_state:
        # Flag: True quando un tool ha modificato il calendario e la sidebar
        # va ricaricata da Google.
        st.session_state.calendar_dirty = True

    if "cal_events" not in st.session_state:
        st.session_state.cal_events = []


# ---------------------------------------------------------------------------
# Caricamento eventi calendario per la sidebar
# ---------------------------------------------------------------------------
def load_calendar_events(days_back: int = 15, days_fwd: int = 45) -> list:
    """
    Legge gli eventi reali da Google Calendar e li converte nel formato
    richiesto da streamlit-calendar (title / start / end).
    """
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
                {
                    "title": e.get("summary", "Senza titolo"),
                    "start": start,
                    "end": end,
                }
            )
        return events
    except Exception as exc:  # noqa: BLE001
        st.sidebar.warning(f"Impossibile caricare il calendario: {exc}")
        return []


# ---------------------------------------------------------------------------
# UI
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

        calendar(
            events=st.session_state.cal_events,
            options=CALENDAR_OPTIONS,
            custom_css=CUSTOM_CSS,
            key="calendar",
        )


def handle_user_input(prompt: str) -> None:
    # Mostra subito il messaggio utente.
    st.session_state.display_messages.append(
        {"role": "user", "avatar": USER_AVATAR, "content": prompt}
    )
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    # Esegue il turno agentico. La callback mostra i tool man mano che
    # vengono chiamati, cosi' l'utente vede che l'agente sta lavorando.
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        with st.status("Sto elaborando la richiesta...", expanded=False) as status:
            def on_tool_call(name: str, args: dict) -> None:
                status.update(label=f"Uso lo strumento: {name}")

            agent = st.session_state.agent
            agent.on_tool_call = on_tool_call
            result = agent.run_turn(st.session_state.history, prompt)
            status.update(label="Fatto", state="complete")

        st.markdown(result.text)

    # Aggiorna gli stati.
    st.session_state.history = result.messages
    st.session_state.display_messages.append(
        {"role": "assistant", "avatar": BOT_AVATAR, "content": result.text}
    )

    # Se l'agente ha toccato il calendario, la sidebar va ricaricata.
    if result.calendar_changed:
        st.session_state.calendar_dirty = True
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    init_state()
    render_header()
    render_chat_history()
    render_sidebar()

    if prompt := st.chat_input("Scrivi una richiesta su mail o calendario..."):
        handle_user_input(prompt)


if __name__ == "__main__":
    main()
