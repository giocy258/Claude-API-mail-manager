"""
tools/gmail.py

Funzioni tool esposte a Claude per la gestione di Gmail.
Adattamento di gmail_agent/tools.py: stessa logica di dominio, unica
differenza e' l'auth condivisa (google_auth.accesso) e il fatto che
tool_datetime_now non vive piu' qui (e' centralizzato in tools/registry.py).
"""

from __future__ import annotations

import re

from .google_auth import accesso
from .gmail_api import read_emails, send_email, trash_email, update_email_labels


def tool_search_gmail(query: str, limit: int = 5) -> str:
    """
    Cerca e legge le email usando la sintassi di ricerca Gmail.

    Esempi di query:
      - "is:unread" -> email non lette
      - "from:amazon" -> email da Amazon
      - "subject:fattura" -> email con 'fattura' nell'oggetto
      - "is:unread from:Giovanni" -> non lette di Giovanni
    """
    creds = accesso()
    emails = read_emails(creds, query=query, max_results=limit)

    if not emails:
        return f"Nessuna email trovata per la query: '{query}'."

    output = [f"Risultati per '{query}':\n"]
    for email in emails:
        snippet_clean = email['snippet'].replace('\n', ' ').strip()
        output.append(
            f"- ID: {email['id']} | [{email['date']}]\n"
            f"  Da: {email['sender']}\n"
            f"  Oggetto: {email['subject']}\n"
            f"  Anteprima: {snippet_clean}..."
        )

    return "\n---\n".join(output)


def tool_find_contacts(name: str) -> str:
    """
    Cerca indirizzi email validi nello storico messaggi basandosi su un nome.
    Da usare SEMPRE prima di inviare un'email se non si ha l'indirizzo esatto.
    """
    creds = accesso()
    query = f"from:{name}"

    emails = read_emails(creds, query=query, max_results=15)

    if not emails:
        return f"Non ho trovato nessun indirizzo email storico associato al nome '{name}'."

    unique_contacts = set()

    for email in emails:
        raw_sender = email['sender']
        match = re.search(r'<([^>]+)>', raw_sender)

        if match:
            email_address = match.group(1)
            display_name = raw_sender.replace(f"<{email_address}>", "").strip().replace('"', '')
        else:
            email_address = raw_sender
            display_name = "N/A"

        if email_address and '@' in email_address:
            if email_address not in [x[1] for x in unique_contacts]:
                unique_contacts.add((display_name, email_address))

    if not unique_contacts:
        return f"Ho trovato email da '{name}', ma non sono riuscito a isolare un indirizzo."

    output_str = f"Contatti trovati per '{name}':\n"
    for display_name, email_address in unique_contacts:
        output_str += f"- {display_name}: {email_address}\n"

    return output_str


def tool_send_email_message(recipient: str, subject: str, text_body: str) -> str:
    """Invia un'email. Richiede l'indirizzo email esatto del destinatario."""
    creds = accesso()
    res = send_email(creds, recipient, subject, text_body)

    if res:
        return f"Email inviata a {recipient}. ID: {res['id']}"
    return "Errore invio email."


def tool_manage_email(msg_id: str, action: str) -> str:
    """
    Gestisce lo stato di un'email.

    Args:
        msg_id: ID del messaggio.
        action: 'mark_read' oppure 'trash'.
    """
    creds = accesso()

    if action == 'mark_read':
        try:
            update_email_labels(creds, msg_id, remove_labels=['UNREAD'])
            return f"Messaggio {msg_id} segnato come letto."
        except Exception as e:
            return f"Errore nel segnare come letto: {e}"

    elif action == 'trash':
        try:
            trash_email(creds, msg_id)
            return f"Messaggio {msg_id} spostato nel cestino."
        except Exception as e:
            return f"Errore cestinamento: {e}"

    else:
        return "Azione non valida. Usa 'mark_read' o 'trash'."
