"""Explicit user intent boundary. Natural language never enables portal tools."""
import re
COMMAND = re.compile(r'^/takt(?:\s+|$)', re.I)
CHAT_RULE = ('Dies ist reiner Chat ohne Portalwerkzeuge. Führe keine TAKT-Aktion aus und behaupte nie, '
             'etwas im Portal gespeichert oder geändert zu haben. Für Portalaufträge muss die Person '
             'ihre Nachricht ausdrücklich mit /takt beginnen, z. B. /takt Erstelle eine Aufgabe. ')


def split(prompt):
    value = (prompt or '').strip()
    match = COMMAND.match(value)
    return (True, value[match.end():].strip()) if match else (False, value)


def clear_pending(request):
    from .main import stash_get
    for key in ('takt-agent-plan','takt-agent-context','takt-agent-private-intake','takt-agent-krank'):
        stash_get(request,key,pop=True)
