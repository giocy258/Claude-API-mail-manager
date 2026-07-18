"""
tools/google_auth.py

Autenticazione Google unificata per Gmail + Calendar.

Adattamento della funzione accesso() originale (duplicata identica in
gmail_agent/gmailapi.py e calendar_agent/calendarapi.py nel progetto ADK):
qui esiste una volta sola, con gli scope di entrambi i servizi uniti, cosi'
un solo consenso OAuth abilita l'agente a operare su entrambi.

La logica di refresh/ri-autenticazione e' invariata rispetto all'originale.
"""

from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Se modifichi questi scope, elimina token.json e rifai il login.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

# credentials.json e token.json vivono in questa stessa cartella (tools/).
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(_BASE_DIR, "token.json")
CREDS_PATH = os.path.join(_BASE_DIR, "credentials.json")


def accesso() -> Credentials:
    """
    Gestisce l'autenticazione Google (Gmail + Calendar) cercando
    credentials.json e token.json in questa cartella.
    """
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Errore durante il refresh del token: {e}")
                # Se il token e' corrotto, lo rimuoviamo e riproviamo.
                if os.path.exists(TOKEN_PATH):
                    os.remove(TOKEN_PATH)
                return accesso()  # Ricorsione sicura per riautenticare
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(
                    f"CRITICO: Non trovo il file credentials.json qui: {CREDS_PATH}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


if __name__ == "__main__":
    # Esecuzione diretta -> genera/aggiorna token.json e conferma lo scope.
    credenziali = accesso()
    print(f"\nAutenticazione riuscita. Token salvato in: {TOKEN_PATH}")
    print(f"Scope concessi: {credenziali.scopes}")
