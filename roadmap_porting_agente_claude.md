# Porting agente Google ADK → Claude API — Documento operativo

Riferimento: progetto sorgente `ML-Project-main` (coordinator + gmail_agent + calendar_agent, ADK). Architettura target: **agente singolo** con tool nativi Claude, testato tramite harness Streamlit.

---

## 1. Roadmap di sviluppo

### Fase 0 — Setup progetto
- [ ] Creare nuovo ambiente Python (>=3.12, coerente col progetto sorgente) con `uv` o `venv`
- [ ] Aggiungere dipendenze: `anthropic`, `streamlit`, `streamlit-calendar`, `python-dotenv`, `google-auth-oauthlib`, `google-api-python-client`, `tzdata`
- [ ] Creare `.env` con `ANTHROPIC_API_KEY` (oltre alle credenziali Google già esistenti)
- [ ] Copiare nel nuovo progetto, invariati: `gmailapi.py`, `calendarapi.py`, `my_parser.py`, `trova_un_buco.py`, i `token.json` / `credentials.json` — nessuna logica di business qui va toccata

### Fase 1 — Consolidamento dei tool
- [ ] Unificare `gmail_agent/tools.py` e `calendar_agent/tools.py` in un unico modulo (es. `tools/gmail.py`, `tools/calendar.py`), riusando le funzioni esistenti quasi 1:1
- [ ] Rivedere i tipi di ritorno: ogni funzione deve restituire una **stringa** (o dato JSON-serializzabile) — es. `tool_datetime_now` va adattato per restituire una stringa ISO invece di un oggetto `datetime`
- [ ] Scrivere per ciascun tool il relativo `input_schema` JSON (nome, descrizione, parametri, tipi, required) — è il lavoro che ADK generava automaticamente dalle type hints

### Fase 2 — Prompt di sistema unico
- [ ] Fondere i contenuti di `coordinator_agent/prompts`, `gmail_agent/prompts`, `calendar_agent/prompts` in un unico system prompt
- [ ] Rimuovere la logica di routing basata su tag `<call:...>` (non più necessaria in architettura single-agent: la scelta del tool la fa Claude nativamente)
- [ ] Mantenere le regole di dominio importanti: es. "cerca sempre il contatto prima di inviare", gestione conflitti calendario, timezone di default `Europe/Rome`

### Fase 3 — Agent core (loop agentico)
- [ ] Creare `agent_core.py` con: client Anthropic, system prompt, lista tool, funzione `run_turn(messages) -> (testo_finale, messages_aggiornati)`
- [ ] Implementare il ciclo: chiamata a `messages.create` → se `stop_reason == "tool_use"` esegui la funzione corrispondente dal registry → accoda `tool_result` → richiama il modello → ripeti fino a risposta testuale finale
- [ ] Gestire errori dei tool (es. token Google scaduto, evento non trovato) restituendo un messaggio d'errore leggibile come `tool_result`, senza far crashare il loop

### Fase 4 — Harness di test (Streamlit)
- [ ] Vedi sezione 2 sotto per il dettaglio architetturale
- [ ] Riutilizzare dove possibile lo scheletro già presente in `streamlit/interface.py` (chat UI, sidebar calendario con `streamlit-calendar`)

### Fase 5 — Testing iterativo
- [ ] Casi singolo dominio: "ho nuove email?", "che impegni ho domani?"
- [ ] Casi multi-step: "trova un contatto e scrivigli un'email", "trova uno slot libero e crea l'evento"
- [ ] Casi ambigui/di chiarimento: nome contatto con più email associate, slot occupato
- [ ] Casi di errore: credenziali scadute, evento inesistente da cancellare

### Fase 6 — Rifinitura
- [ ] Logging delle chiamate tool (utile in debug, anche solo su console)
- [ ] Eventuale limite su numero di iterazioni del loop (safety contro loop infiniti)
- [ ] Rivedere il system prompt sulla base degli errori osservati in Fase 5

### Fase 7 — Estensioni future (solo da annotare ora, non da sviluppare subito)
- Persistenza della sessione tra riavvii (oggi si perde tutto alla chiusura di Streamlit)
- Deploy (es. come servizio invece che solo app locale)
- Eventuale ritorno a un'architettura multi-agente se la complessità dei task crescerà

---

## 2. Architettura dell'harness Streamlit

### Componenti

| Componente | File | Responsabilità |
|---|---|---|
| Streamlit UI | `app.py` | Chat + sidebar calendario, mostra messaggi, invia input all'agent core |
| Agent core | `agent_core.py` | Loop agentico: dialoga con Claude API, esegue tool, ritorna risposta finale |
| Tools registry | `tools/registry.py` | Mappa nome-tool → funzione Python + relativo `input_schema` |
| Tool Gmail/Calendar | `tools/gmail.py`, `tools/calendar.py` | Logica di dominio, riusata dal progetto originale |
| Google APIs | `gmailapi.py`, `calendarapi.py` | Autenticazione OAuth e chiamate reali, invariate |

### Flusso dati

1. L'utente scrive nella chat Streamlit → il messaggio viene accodato a `st.session_state.messages` (formato nativo Anthropic: `{"role": "user", "content": ...}`)
2. `agent_core.run_turn()` riceve l'intera history e la invia a Claude con system prompt + lista tool
3. Se Claude risponde con `stop_reason == "tool_use"`: l'agent core guarda il registry, esegue la funzione, e accoda il `tool_result` ai messages; il ciclo richiama Claude
4. Quando arriva una risposta testuale finale, questa viene mostrata in chat e salvata in `session_state`
5. Se il tool eseguito ha toccato il calendario, la sidebar (`streamlit-calendar`) viene aggiornata rileggendo gli eventi

### Punto importante sullo state

Da tenere distinti due concetti, spesso confusi nello scheletro originale:
- **`session_state.messages`**: la history nel formato richiesto dall'API Anthropic (necessaria per il contesto del modello, include anche i blocchi `tool_use`/`tool_result`)
- **`session_state.display_messages`** (opzionale ma consigliato): solo i messaggi testuali da mostrare in chat, per non esporre in UI i dettagli tecnici delle chiamate tool

### Struttura cartelle proposta

```
project/
├── .env
├── app.py                  # Streamlit — punto di ingresso
├── agent_core.py           # loop agentico
├── system_prompt.md        # prompt unificato (fusione dei 3 originali)
├── tools/
│   ├── registry.py         # nome → (funzione, schema)
│   ├── gmail.py
│   ├── calendar.py
│   ├── gmailapi.py         # invariato dal progetto originale
│   ├── calendarapi.py      # invariato dal progetto originale
│   ├── my_parser.py
│   └── trova_un_buco.py
├── credentials.json / token.json
└── streamlit_assets/
    ├── cal_config.py       # riusato dal progetto originale
    └── cal_events.json
```

### Cosa riusare dallo scheletro Streamlit esistente

- Struttura chat (`st.chat_input`, `st.chat_message`, `session_state.messages`)
- Sidebar calendario con `streamlit_calendar` e `cal_config.py`
- Bottoni di collegamento rapido a Gmail/Calendar web

### Cosa va riscritto

- La chiamata `root_agent.run(...)` (specifica di ADK) va sostituita dalla chiamata al loop `agent_core.run_turn(...)`
- Il file presenta ancora marcatori di conflitto Git irrisolti (`<<<<<<< HEAD` / `=======` / `>>>>>>>`) — va ripulito prima di essere riutilizzato come base
- Il caricamento eventi calendario andrebbe reso dinamico (oggi legge un `cal_events.json` statico) collegandolo a `tool_list_upcoming_events`, così la sidebar riflette lo stato reale del calendario

---

## 3. Prossimo passo naturale

Con questo documento come riferimento, il prossimo step concreto è implementare `agent_core.py` (il loop agentico) e il `tools/registry.py`, che sono i due moduli da cui dipende sia il funzionamento dell'agente sia l'harness di test.
