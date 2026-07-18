"""
tools/calendar_api.py

Layer di chiamate dirette alla Google Calendar API. Adattamento di
calendar_agent/calendarapi.py: stessa logica, stesso filtro sull'intervallo
di date; l'autenticazione ora viene da google_auth.accesso() (condivisa con
Gmail) invece di una accesso() locale.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # richiede tzdata

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import my_parser


def read_calendar(creds: Credentials, date_info: dict) -> list:
    """
    Legge gli eventi da Google Calendar per un intervallo di date specificato.

    Args:
        creds: Credenziali per accedere all'API di Google Calendar.
        date_info: Dizionario con "start" e "end" in formato YYYY-MM-DD.

    Returns:
        Lista di eventi (dizionari) nell'intervallo richiesto.
    """
    try:
        local_tz = ZoneInfo("Europe/Rome")
    except ZoneInfoNotFoundError:
        print("Fuso orario non trovato. Assicurati che tzdata sia installato ('pip install tzdata')")
        raise

    try:
        service = build("calendar", "v3", credentials=creds)
        all_events = []

        start_date = datetime.datetime.fromisoformat(date_info["start"])
        end_date = datetime.datetime.fromisoformat(date_info["end"])

        current_date = start_date

        while current_date <= end_date:
            start_of_day_local = datetime.datetime(
                current_date.year, current_date.month, current_date.day,
                0, 0, 0, tzinfo=local_tz
            )
            end_of_day_local = datetime.datetime(
                current_date.year, current_date.month, current_date.day,
                23, 59, 0, tzinfo=local_tz
            )

            start_of_day_utc = start_of_day_local.astimezone(datetime.timezone.utc).isoformat()
            end_of_day_utc = end_of_day_local.astimezone(datetime.timezone.utc).isoformat()

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_of_day_utc,
                    timeMax=end_of_day_utc,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            if events:
                all_events.extend(events)

            current_date += datetime.timedelta(days=1)

        return all_events

    except HttpError as error:
        print(f"Si è verificato un errore durante la lettura: {error}")
        return []


def add_calendar(creds: Credentials, event: dict) -> dict:
    """
    Aggiunge un singolo evento a Google Calendar.

    Args:
        creds: Credenziali per l'accesso all'API.
        event: Dizionario grezzo, formattato internamente con my_parser.format_event.
    """
    try:
        service = build("calendar", "v3", credentials=creds)
        formatted = my_parser.format_event(event)
        evento = service.events().insert(calendarId="primary", body=formatted).execute()
        return evento
    except HttpError as error:
        print(f"Errore durante il caricamento dell'evento: {error}")
        raise


def delete_calendar(creds: Credentials, event: dict) -> None:
    """Elimina un singolo evento da Google Calendar."""
    try:
        service = build("calendar", "v3", credentials=creds)
        event_id = event.get('id')
        service.events().delete(calendarId='primary', eventId=event_id).execute()
    except HttpError as error:
        print(f"Errore durante l'eliminazione dell'evento '{event.get('summary', 'Senza titolo')}': {error}")
        raise


def update_calendar(creds: Credentials, old_event: dict, new_event: dict) -> None:
    """Aggiorna un evento esistente nel calendario."""
    try:
        service = build("calendar", "v3", credentials=creds)
        event_id = old_event.get('id')
        formatted = my_parser.format_event(new_event)
        service.events().update(calendarId='primary', eventId=event_id, body=formatted).execute()
    except HttpError as error:
        print(f"Errore durante l'aggiornamento dell'evento '{old_event.get('summary', 'Senza titolo')}': {error}")
        raise


def get_available_colors(creds: Credentials):
    try:
        service = build("calendar", "v3", credentials=creds)
        colors = service.colors().get().execute()
        return colors['event']
    except HttpError as error:
        print(f"Errore nel recupero colori: {error}")
        return None
