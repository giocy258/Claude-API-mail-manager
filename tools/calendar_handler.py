"""
tools/calendar.py

Funzioni tool esposte a Claude per la gestione di Google Calendar.
Adattamento di calendar_agent/tools.py: stessa logica di dominio, unica
differenza e' l'auth condivisa (google_auth.accesso) e il fatto che
tool_datetime_now non vive piu' qui (e' centralizzato in tools/registry.py).
"""

from __future__ import annotations

import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from .google_auth import accesso
from .calendar_api import add_calendar, delete_calendar, read_calendar, update_calendar
from .trova_un_buco import trova_slot_alternativo

ROME_TZ = ZoneInfo("Europe/Rome")


def tool_list_upcoming_events(days: int = 7) -> str:
    """Elenca gli eventi in calendario per i prossimi N giorni."""
    creds = accesso()
    start_date = datetime.datetime.now(ROME_TZ)
    end_date = start_date + datetime.timedelta(days=days)

    date_info = {
        "start": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d"),
    }

    events = read_calendar(creds, date_info)

    if not events:
        return "Nessun evento trovato nei prossimi giorni."

    output_list = []
    for e in events:
        start_dt_str = e["start"].get("dateTime", e["start"].get("date"))
        summary = e.get("summary", "Senza titolo")

        if 'T' in start_dt_str:
            start_dt = datetime.datetime.fromisoformat(start_dt_str).astimezone(ROME_TZ)
            formatted_time = start_dt.strftime("%d/%m %H:%M")
        else:
            formatted_time = start_dt_str

        output_list.append(f"- {formatted_time}: {summary}")

    return "\n".join(output_list)


def tool_find_availability(duration_minutes: int, days_to_check: int = 5) -> str:
    """Trova il primo slot libero. Da usare quando l'utente chiede 'quando sono libero?'."""
    creds = accesso()
    return trova_slot_alternativo(
        creds=creds,
        duration_minutes=duration_minutes,
        search_days=days_to_check,
        buffer_minutes=30,
    )


def tool_safe_add_event(
    summary: str, start_iso: str, end_iso: str, location: Optional[str] = None
) -> str:
    """
    Metodo PREFERITO per creare un evento: lo aggiunge solo se lo slot e' libero,
    altrimenti suggerisce un'alternativa senza creare nulla.
    """
    creds = accesso()

    try:
        start_dt = datetime.datetime.fromisoformat(start_iso)
        end_dt = datetime.datetime.fromisoformat(end_iso)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=ROME_TZ)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=ROME_TZ)
    except ValueError:
        return "Errore: Formato data non valido. Usa ISO (YYYY-MM-DDTHH:MM:SS)."

    date_info = {
        "start": start_dt.date().isoformat(),
        "end": end_dt.date().isoformat(),
    }
    existing_events = read_calendar(creds, date_info)

    is_busy = False
    for event in existing_events:
        ev_start_str = event['start'].get('dateTime')
        ev_end_str = event['end'].get('dateTime')

        if ev_start_str and ev_end_str:
            ev_start = datetime.datetime.fromisoformat(ev_start_str).astimezone(ROME_TZ)
            ev_end = datetime.datetime.fromisoformat(ev_end_str).astimezone(ROME_TZ)

            if (start_dt < ev_end) and (end_dt > ev_start):
                is_busy = True
                break

    if is_busy:
        duration = int((end_dt - start_dt).total_seconds() / 60)
        suggerimento = trova_slot_alternativo(
            creds,
            duration_minutes=duration,
            start_search_from=start_dt,
            search_days=3,
        )
        return f"Slot occupato. {suggerimento}"

    event_dict = {
        "summary": summary,
        "location": location if location else None,
        "start": {"dateTime": start_iso, "timeZone": "Europe/Rome"},
        "end": {"dateTime": end_iso, "timeZone": "Europe/Rome"},
    }
    try:
        add_calendar(creds, event_dict)
        location_info = f" presso '{location}'" if location else ""
        return f"Evento '{summary}' aggiunto correttamente{location_info}: {start_iso}"
    except Exception as e:
        return f"Errore API: {e}"


def tool_force_add_event(
    summary: str, start_iso: str, end_iso: str, location: Optional[str] = None
) -> str:
    """
    Crea un evento IGNORANDO i conflitti. Da usare solo su ordine esplicito
    dell'utente, dopo che tool_safe_add_event ha gia' segnalato uno slot occupato.
    """
    creds = accesso()
    event_dict = {
        "summary": summary,
        "location": location if location else None,
        "start": {"dateTime": start_iso, "timeZone": "Europe/Rome"},
        "end": {"dateTime": end_iso, "timeZone": "Europe/Rome"},
    }
    try:
        add_calendar(creds, event_dict)
    except Exception as e:
        return f"Errore API: {e}"

    location_info = f" presso '{location}'" if location else ""
    return f"Evento forzato aggiunto{location_info}: {summary}"


def tool_delete_event(summary: str, date_iso: str) -> str:
    """Elimina un evento specifico. Richiede il titolo e la data di inizio."""
    creds = accesso()

    try:
        target_date = datetime.datetime.fromisoformat(date_iso)
    except ValueError:
        return "Errore: Data non valida. Usa formato ISO (YYYY-MM-DDTHH:MM:SS)."

    date_info = {
        "start": target_date.date().isoformat(),
        "end": target_date.date().isoformat(),
    }
    events = read_calendar(creds, date_info)

    target_event = None
    for e in events:
        if summary.lower() in e.get("summary", "").lower():
            start_str = e["start"].get("dateTime", e["start"].get("date"))
            if start_str.startswith(date_iso.split("T")[0]):
                target_event = e
                break

    if not target_event:
        return f"Non ho trovato nessun evento chiamato '{summary}' in quella data da cancellare."

    try:
        delete_calendar(creds, target_event)
        return f"Evento '{summary}' eliminato correttamente."
    except Exception as e:
        return f"Errore tecnico durante l'eliminazione: {str(e)}"


def tool_update_event(
    old_summary: str,
    old_date_iso: Optional[str] = None,
    new_summary: Optional[str] = None,
    new_start_iso: Optional[str] = None,
    new_end_iso: Optional[str] = None,
    new_location: Optional[str] = None,
) -> str:
    """
    Modifica un evento esistente. Cerca l'evento originale tramite
    old_summary/old_date_iso e applica solo i campi new_* forniti.
    """
    creds = accesso()

    if not old_date_iso:
        return "Errore: 'old_date_iso' è obbligatorio per trovare l'evento da aggiornare."

    try:
        target_date = datetime.datetime.fromisoformat(old_date_iso)
    except ValueError:
        return "Errore formato data ricerca."

    date_info = {
        "start": target_date.date().isoformat(),
        "end": target_date.date().isoformat(),
    }
    events = read_calendar(creds, date_info)

    old_event_obj: Optional[Dict] = None
    for e in events:
        if old_summary.lower() in e.get("summary", "").lower():
            old_event_obj = e
            break

    if not old_event_obj:
        return f"Non ho trovato l'evento '{old_summary}' da modificare."

    new_event_dict = {
        "summary": new_summary if new_summary is not None else old_event_obj.get("summary"),
        "description": old_event_obj.get("description", ""),
        "location": new_location if new_location is not None else old_event_obj.get("location", ""),
    }

    if new_start_iso and new_end_iso:
        new_event_dict["start"] = {"dateTime": new_start_iso, "timeZone": "Europe/Rome"}
        new_event_dict["end"] = {"dateTime": new_end_iso, "timeZone": "Europe/Rome"}
    else:
        new_event_dict["start"] = old_event_obj.get("start")
        new_event_dict["end"] = old_event_obj.get("end")

    try:
        update_calendar(creds, old_event_obj, new_event_dict)
        return "Evento aggiornato con successo."
    except Exception as e:
        return f"Errore aggiornamento: {str(e)}"
