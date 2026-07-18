"""
tools/registry.py

Registro centrale dei tool esposti a Claude.

Contiene due cose, tenute volutamente vicine per evitare che divergano:
  1. TOOL_SCHEMAS  -> la lista di definizioni JSON inviata all'API Anthropic
  2. TOOL_FUNCTIONS -> la mappa nome_tool -> funzione Python da eseguire

In ADK gli schemi venivano derivati automaticamente dalle type hints e dalle
docstring. Qui vanno dichiarati esplicitamente: e' l'unico "costo" del porting,
ma e' anche un vantaggio, perche' la descrizione che il modello legge diventa
un artefatto di prompt engineering che possiamo curare in modo indipendente
dal codice.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo

from .calendar import (
    tool_delete_event,
    tool_find_availability,
    tool_force_add_event,
    tool_list_upcoming_events,
    tool_safe_add_event,
    tool_update_event,
)
from .gmail import (
    tool_find_contacts,
    tool_manage_email,
    tool_search_gmail,
    tool_send_email_message,
)

DEFAULT_TZ = "Europe/Rome"


# ---------------------------------------------------------------------------
# Tool trasversale
# ---------------------------------------------------------------------------
# Nel progetto ADK questa funzione era duplicata in gmail_agent e calendar_agent
# e restituiva un oggetto datetime. Qui esiste una volta sola e restituisce una
# stringa: i tool_result inviati all'API devono essere serializzabili.
def tool_datetime_now(tz_name: str = DEFAULT_TZ) -> str:
    """Restituisce data e ora correnti come stringa ISO localizzata."""
    return datetime.datetime.now(ZoneInfo(tz_name)).isoformat()


# ---------------------------------------------------------------------------
# Schemi (cio' che il modello vede)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "tool_datetime_now",
        "description": (
            "Restituisce la data e l'ora correnti come stringa ISO. "
            "Da chiamare SEMPRE per prima cosa quando l'utente usa riferimenti "
            "temporali relativi come 'oggi', 'domani', 'la prossima settimana', "
            "prima di calcolare qualsiasi data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tz_name": {
                    "type": "string",
                    "description": f"Fuso orario IANA. Default '{DEFAULT_TZ}'.",
                }
            },
            "required": [],
        },
    },
    # ---------------------------- Gmail ------------------------------------
    {
        "name": "tool_search_gmail",
        "description": (
            "Cerca e legge email usando la sintassi di ricerca nativa di Gmail. "
            "Esempi di query: 'is:unread', 'from:amazon', 'subject:fattura', "
            "'is:unread from:Giovanni'. Restituisce ID, mittente, oggetto e "
            "anteprima di ogni messaggio trovato."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query in sintassi Gmail.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero massimo di risultati. Default 5.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "tool_find_contacts",
        "description": (
            "Cerca indirizzi email nello storico dei messaggi partendo da un nome. "
            "Va usato SEMPRE prima di inviare un'email quando non si conosce "
            "l'indirizzo esatto del destinatario. Se restituisce piu' contatti, "
            "chiedere conferma all'utente invece di indovinare."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome o parte del nome del contatto da cercare.",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "tool_send_email_message",
        "description": (
            "Invia un'email. Richiede l'indirizzo esatto del destinatario, "
            "tipicamente ottenuto prima con tool_find_contacts. "
            "Azione irreversibile: chiedere conferma all'utente prima di usarlo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient": {
                    "type": "string",
                    "description": "Indirizzo email completo del destinatario.",
                },
                "subject": {"type": "string", "description": "Oggetto dell'email."},
                "text_body": {"type": "string", "description": "Corpo del messaggio."},
            },
            "required": ["recipient", "subject", "text_body"],
        },
    },
    {
        "name": "tool_manage_email",
        "description": (
            "Cambia lo stato di un'email: la segna come letta oppure la cestina. "
            "Richiede l'ID del messaggio, ottenibile da tool_search_gmail."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "msg_id": {
                    "type": "string",
                    "description": "ID del messaggio Gmail.",
                },
                "action": {
                    "type": "string",
                    "enum": ["mark_read", "trash"],
                    "description": "Azione da eseguire sul messaggio.",
                },
            },
            "required": ["msg_id", "action"],
        },
    },
    # --------------------------- Calendar ----------------------------------
    {
        "name": "tool_list_upcoming_events",
        "description": (
            "Elenca gli eventi in calendario per i prossimi N giorni a partire "
            "da adesso. Da usare per domande tipo 'che impegni ho?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Giorni da coprire a partire da oggi. Default 7.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "tool_find_availability",
        "description": (
            "Trova il primo slot libero in calendario di una data durata. "
            "Da usare per domande tipo 'quando sono libero?' o quando serve "
            "proporre un orario all'utente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_minutes": {
                    "type": "integer",
                    "description": "Durata richiesta dello slot, in minuti.",
                },
                "days_to_check": {
                    "type": "integer",
                    "description": "Giorni in cui cercare. Default 5.",
                },
            },
            "required": ["duration_minutes"],
        },
    },
    {
        "name": "tool_safe_add_event",
        "description": (
            "Metodo PREFERITO per creare un evento: lo aggiunge solo se lo slot "
            "e' libero, altrimenti restituisce un suggerimento di orario "
            "alternativo senza creare nulla. Le date vanno in formato ISO. "
            "Se lo slot risulta occupato, riferire l'alternativa all'utente e "
            "attendere conferma."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Titolo dell'evento."},
                "start_iso": {
                    "type": "string",
                    "description": "Inizio in formato ISO (YYYY-MM-DDTHH:MM:SS).",
                },
                "end_iso": {
                    "type": "string",
                    "description": "Fine in formato ISO (YYYY-MM-DDTHH:MM:SS).",
                },
                "location": {
                    "type": "string",
                    "description": "Luogo dell'evento (opzionale).",
                },
            },
            "required": ["summary", "start_iso", "end_iso"],
        },
    },
    {
        "name": "tool_force_add_event",
        "description": (
            "Crea un evento IGNORANDO i conflitti di calendario. Da usare solo "
            "su ordine esplicito dell'utente, dopo che tool_safe_add_event ha "
            "gia' segnalato lo slot come occupato. Non usarlo di iniziativa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Titolo dell'evento."},
                "start_iso": {"type": "string", "description": "Inizio in formato ISO."},
                "end_iso": {"type": "string", "description": "Fine in formato ISO."},
                "location": {
                    "type": "string",
                    "description": "Luogo dell'evento (opzionale).",
                },
            },
            "required": ["summary", "start_iso", "end_iso"],
        },
    },
    {
        "name": "tool_delete_event",
        "description": (
            "Elimina un evento dal calendario. Richiede il titolo e la data di "
            "inizio. Azione irreversibile: chiedere conferma prima di usarlo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Titolo dell'evento da eliminare.",
                },
                "date_iso": {
                    "type": "string",
                    "description": "Data di inizio dell'evento in formato ISO.",
                },
            },
            "required": ["summary", "date_iso"],
        },
    },
    {
        "name": "tool_update_event",
        "description": (
            "Modifica un evento esistente. Servono titolo e data attuali per "
            "individuarlo; i campi 'new_*' sono opzionali e vanno passati solo "
            "per cio' che cambia davvero. Se si spostano gli orari, passare "
            "sia new_start_iso sia new_end_iso."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "old_summary": {
                    "type": "string",
                    "description": "Titolo attuale dell'evento.",
                },
                "old_date_iso": {
                    "type": "string",
                    "description": "Data attuale dell'evento in formato ISO.",
                },
                "new_summary": {"type": "string", "description": "Nuovo titolo."},
                "new_start_iso": {"type": "string", "description": "Nuovo inizio ISO."},
                "new_end_iso": {"type": "string", "description": "Nuova fine ISO."},
                "new_location": {"type": "string", "description": "Nuovo luogo."},
            },
            "required": ["old_summary", "old_date_iso"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch (cio' che viene realmente eseguito)
# ---------------------------------------------------------------------------
TOOL_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "tool_datetime_now": tool_datetime_now,
    "tool_search_gmail": tool_search_gmail,
    "tool_find_contacts": tool_find_contacts,
    "tool_send_email_message": tool_send_email_message,
    "tool_manage_email": tool_manage_email,
    "tool_list_upcoming_events": tool_list_upcoming_events,
    "tool_find_availability": tool_find_availability,
    "tool_safe_add_event": tool_safe_add_event,
    "tool_force_add_event": tool_force_add_event,
    "tool_delete_event": tool_delete_event,
    "tool_update_event": tool_update_event,
}

# I tool che modificano lo stato del calendario: l'harness Streamlit li usa per
# sapere quando ricaricare la sidebar.
CALENDAR_MUTATING_TOOLS = {
    "tool_safe_add_event",
    "tool_force_add_event",
    "tool_delete_event",
    "tool_update_event",
}


def execute_tool(name: str, tool_input: Dict[str, Any]) -> str:
    """
    Esegue un tool e ne restituisce SEMPRE una stringa.

    Non solleva mai eccezioni verso l'alto: un errore di un tool (token Google
    scaduto, evento inesistente, argomento sbagliato) viene trasformato in un
    messaggio testuale che torna al modello come tool_result. Cosi' Claude puo'
    accorgersi del problema e reagire (riprovare, chiedere all'utente), invece
    di far esplodere il loop.
    """
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Errore: tool sconosciuto '{name}'."

    try:
        result = func(**tool_input)
    except TypeError as exc:
        return f"Errore: argomenti non validi per '{name}' -> {exc}"
    except Exception as exc:  # noqa: BLE001 - vogliamo davvero catturare tutto
        return f"Errore durante l'esecuzione di '{name}': {type(exc).__name__}: {exc}"

    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def sanity_check() -> None:
    """Verifica che schemi e funzioni siano allineati. Utile in fase di sviluppo."""
    schema_names = {s["name"] for s in TOOL_SCHEMAS}
    func_names = set(TOOL_FUNCTIONS)

    only_schema = schema_names - func_names
    only_func = func_names - schema_names

    if only_schema:
        raise RuntimeError(f"Schemi senza funzione corrispondente: {only_schema}")
    if only_func:
        raise RuntimeError(f"Funzioni senza schema corrispondente: {only_func}")
