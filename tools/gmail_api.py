"""
tools/gmail_api.py

Layer di chiamate dirette alla Gmail API. Adattamento di gmail_agent/gmailapi.py:
stessa logica, unica differenza e' che l'autenticazione ora viene da
google_auth.accesso() (condivisa con Calendar) invece di una accesso() locale.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials


def read_emails(creds: Credentials, query: str = 'is:unread', max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Legge le email da Gmail basandosi su una query.

    Returns:
        Lista di dizionari con keys: id, threadId, subject, sender, snippet, date.
    """
    try:
        service = build("gmail", "v1", credentials=creds)

        results = service.users().messages().list(
            userId='me', q=query, maxResults=max_results
        ).execute()
        messages = results.get('messages', [])

        if not messages:
            return []

        parsed_messages = []
        for msg in messages:
            txt = service.users().messages().get(
                userId='me', id=msg['id'], format='full'
            ).execute()

            payload = txt.get('payload', {})
            headers = payload.get('headers', [])

            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "(Nessun Oggetto)")
            sender = next((h['value'] for h in headers if h['name'] == 'From'), "Sconosciuto")
            date_sent = next((h['value'] for h in headers if h['name'] == 'Date'), "")
            snippet = txt.get('snippet', "")

            parsed_messages.append({
                "id": msg['id'],
                "threadId": msg['threadId'],
                "subject": subject,
                "sender": sender,
                "date": date_sent,
                "snippet": snippet,
            })

        return parsed_messages

    except HttpError as error:
        print(f"Si è verificato un errore durante la lettura delle email: {error}")
        return []


def send_email(creds: Credentials, to: str, subject: str, body: str) -> Optional[Dict]:
    """Invia un'email."""
    try:
        service = build("gmail", "v1", credentials=creds)

        message = EmailMessage()
        message.set_content(body)
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        sent_message = service.users().messages().send(
            userId="me", body=create_message
        ).execute()

        return sent_message

    except HttpError as error:
        print(f"Errore durante l'invio dell'email: {error}")
        return None


def trash_email(creds: Credentials, msg_id: str) -> None:
    """Sposta un'email nel cestino."""
    try:
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().trash(userId='me', id=msg_id).execute()
    except HttpError as error:
        print(f"Errore durante l'eliminazione dell'email: {error}")
        raise


def update_email_labels(
    creds: Credentials,
    msg_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> None:
    """
    Modifica le etichette di un'email.
    Utile per segnare come letto (remove_labels=['UNREAD']) o archiviare (remove_labels=['INBOX']).
    """
    try:
        service = build("gmail", "v1", credentials=creds)
        body = {
            "addLabelIds": add_labels or [],
            "removeLabelIds": remove_labels or [],
        }
        service.users().messages().modify(userId='me', id=msg_id, body=body).execute()
    except HttpError as error:
        print(f"Errore durante l'aggiornamento etichette: {error}")
        raise
