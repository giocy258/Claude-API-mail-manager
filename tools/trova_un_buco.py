import datetime
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def trova_slot_alternativo(
    creds: Credentials,
    duration_minutes: int,
    start_search_from: datetime.datetime = None,
    search_days: int = 3,
    buffer_minutes: int = 30,
) -> str:
    """
    Trova il primo slot libero disponibile.
    Gestisce correttamente la conversione delle stringhe ISO di Google in oggetti datetime.
    """
    local_tz = ZoneInfo("Europe/Rome")

    if start_search_from:
        now_local = start_search_from
        if now_local.tzinfo is None:
            now_local = now_local.replace(tzinfo=local_tz)
    else:
        now_local = datetime.datetime.now(local_tz)

    try:
        service = build("calendar", "v3", credentials=creds)

        current_search_time = now_local
        minutes = (current_search_time.minute // 15 + 1) * 15
        current_search_time = current_search_time.replace(
            minute=0, second=0, microsecond=0
        ) + datetime.timedelta(minutes=minutes)

        days_checked = 0

        while days_checked < search_days:
            day_start_limit = current_search_time.replace(hour=8, minute=0, second=0, microsecond=0)
            day_end_limit = current_search_time.replace(hour=20, minute=0, second=0, microsecond=0)

            if current_search_time >= day_end_limit:
                current_search_time = day_start_limit + datetime.timedelta(days=1)
                days_checked += 1
                continue

            if current_search_time < day_start_limit:
                current_search_time = day_start_limit

            events_result = service.events().list(
                calendarId='primary',
                timeMin=day_start_limit.isoformat(),
                timeMax=day_end_limit.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])

            for event in events:
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                end_str = event['end'].get('dateTime', event['end'].get('date'))

                try:
                    if "T" not in start_str:
                        continue
                    start_busy = datetime.datetime.fromisoformat(start_str)
                    end_busy = datetime.datetime.fromisoformat(end_str)
                except ValueError:
                    continue

                start_busy = start_busy - datetime.timedelta(minutes=buffer_minutes)
                end_busy = end_busy + datetime.timedelta(minutes=buffer_minutes)

                slot_end = current_search_time + datetime.timedelta(minutes=duration_minutes)

                if (current_search_time < end_busy) and (slot_end > start_busy):
                    current_search_time = end_busy
                    if current_search_time.second > 0:
                        current_search_time = current_search_time + datetime.timedelta(minutes=1)
                    current_search_time = current_search_time.replace(second=0, microsecond=0)

            final_slot_end = current_search_time + datetime.timedelta(minutes=duration_minutes)

            if final_slot_end <= day_end_limit:
                formatted_time = current_search_time.strftime('%A %d/%m alle %H:%M')
                return f"Slot trovato: {formatted_time} (Durata: {duration_minutes} min)"

            current_search_time = day_start_limit + datetime.timedelta(days=1)
            days_checked += 1

        return "Nessuno slot libero trovato nei prossimi giorni."

    except Exception as e:
        return f"Errore durante la ricerca slot: {str(e)}"
