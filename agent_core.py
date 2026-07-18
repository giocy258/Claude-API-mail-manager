"""
agent_core.py

Il loop agentico. E' il pezzo che ADK eseguiva per te e che qui scriviamo
esplicitamente: chiedi al modello, se chiede un tool eseguilo, restituiscigli
il risultato, ripeti finche' non produce una risposta testuale finale.

Il modulo e' volutamente ignaro di Streamlit: riceve una history e la
restituisce aggiornata. Questo permette di usarlo identico da CLI, da
Streamlit o da test automatici.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic
from dotenv import load_dotenv

from tools.registry import (
    CALENDAR_MUTATING_TOOLS,
    TOOL_SCHEMAS,
    execute_tool,
    sanity_check,
)

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 2048
# Guardia contro loop infiniti: un turno non dovrebbe mai richiedere piu' di
# questo numero di round-trip col modello.
MAX_ITERATIONS = 10

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "Sei un assistente personale che gestisce Gmail e Google Calendar "
        "dell'utente tramite i tool a disposizione."
    )


@dataclass
class TurnResult:
    """Esito di un turno completo (input utente -> risposta finale)."""

    text: str
    messages: List[Dict[str, Any]]
    tool_calls: List[str] = field(default_factory=list)

    @property
    def calendar_changed(self) -> bool:
        """True se durante il turno il calendario e' stato modificato."""
        return any(name in CALENDAR_MUTATING_TOOLS for name in self.tool_calls)


class AgentCore:
    """
    Incapsula client, system prompt e loop.

    Uso tipico:
        agent = AgentCore()
        result = agent.run_turn(messages, "che impegni ho domani?")
        print(result.text)
        messages = result.messages   # history aggiornata, da riusare al turno dopo
    """

    def __init__(
        self,
        model: str = MODEL,
        system_prompt: Optional[str] = None,
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        sanity_check()
        self.client = Anthropic()  # legge ANTHROPIC_API_KEY dall'ambiente
        self.model = model
        self.system_prompt = system_prompt or _load_system_prompt()
        # Callback opzionale: l'harness la usa per mostrare in UI cosa sta
        # facendo l'agente mentre lo fa ("sto cercando le tue email...").
        self.on_tool_call = on_tool_call

    def run_turn(
        self,
        messages: List[Dict[str, Any]],
        user_input: Optional[str] = None,
    ) -> TurnResult:
        """
        Esegue un turno completo.

        `messages` e' la history nel formato nativo dell'API Anthropic e viene
        copiata, non mutata in place: chi chiama decide se adottare la nuova
        versione. Se `user_input` e' passato, viene accodato come messaggio
        utente prima di iniziare.
        """
        convo = list(messages)
        if user_input is not None:
            convo.append({"role": "user", "content": user_input})

        tool_calls: List[str] = []

        for _ in range(MAX_ITERATIONS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self.system_prompt,
                tools=TOOL_SCHEMAS,
                messages=convo,
            )

            # La risposta dell'assistente va sempre accodata cosi' com'e',
            # inclusi i blocchi tool_use: l'API richiede che ogni tool_use sia
            # seguito dal tool_result corrispondente nel messaggio successivo.
            convo.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return TurnResult(
                    text=_extract_text(response.content),
                    messages=convo,
                    tool_calls=tool_calls,
                )

            # Un singolo messaggio puo' contenere piu' tool_use: vanno eseguiti
            # tutti e i risultati raccolti in UN solo messaggio user.
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_calls.append(block.name)
                if self.on_tool_call:
                    self.on_tool_call(block.name, block.input)

                output = execute_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }
                )

            convo.append({"role": "user", "content": tool_results})

        return TurnResult(
            text=(
                "Ho raggiunto il limite di passaggi senza arrivare a una "
                "risposta. Puoi riformulare la richiesta in modo piu' semplice?"
            ),
            messages=convo,
            tool_calls=tool_calls,
        )


def _extract_text(content: List[Any]) -> str:
    """Concatena i blocchi testuali di una risposta, scartando il resto."""
    parts = [block.text for block in content if block.type == "text"]
    return "\n".join(parts).strip()


if __name__ == "__main__":
    # Harness minimale da CLI: utile per testare il loop prima ancora di
    # avere l'interfaccia Streamlit.
    agent = AgentCore(
        on_tool_call=lambda name, args: print(f"  [tool] {name}({args})")
    )
    history: List[Dict[str, Any]] = []

    print("Agente pronto. Ctrl+C per uscire.\n")
    while True:
        try:
            user_msg = input("Tu: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCiao!")
            break

        if not user_msg:
            continue

        result = agent.run_turn(history, user_msg)
        history = result.messages
        print(f"\nAgente: {result.text}\n")
