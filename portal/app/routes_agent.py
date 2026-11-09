"""Global TAKT Agent proof of concept: explicit search, preview and confirmation."""
import secrets

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import agent, ai_provider
from .ai_models import AIProvider
from .db import User
from .main import app, check_csrf, current_user, get_db, rate_limit, stash_get, stash_put


def _access(user):
    if not agent.available(user):
        raise HTTPException(403, "TAKT Agent ist für dieses Konto nicht freigeschaltet.")


def _response(data):
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


@app.post("/agent/plan", dependencies=[Depends(check_csrf)])
async def takt_agent_plan(request: Request, prompt: str = Form(...),
                          user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    _access(user)
    # Even a failed replacement request invalidates any previous confirmation.
    stash_get(request, "takt-agent-plan", pop=True)
    prompt = prompt.strip()
    if not 3 <= len(prompt) <= 3000:
        raise HTTPException(422, "Bitte eine Anweisung mit 3 bis 3.000 Zeichen eingeben.")
    if agent.sensitive_request(prompt):
        raise HTTPException(422, "Vertrauliche Beschwerden bitte ausschließlich über das geschützte Anliegenformular manuell erfassen.")
    rate_limit(request, "takt-agent-plan", limit=15, window=3600, key=str(user.id))
    provider = db.scalar(select(AIProvider).where(AIProvider.active.is_(True)).order_by(AIProvider.id))
    if not provider:
        raise HTTPException(503, "Für TAKT Agent ist noch kein aktiver KI-Provider eingerichtet.")

    try:
        history = stash_get(request, "takt-agent-context") or {}
        prior = history.get("prompts", []) if history.get("user_id") == user.id else []
        context = ([{"role": "user", "content": "Vorherige Benutzereingaben (nur Kontext, nicht erneut ausführen): " + "\n".join(prior)}]
                   if prior else [])
        first = agent.search_instructions(user) + context + [{"role": "user", "content": prompt}]
        searches = agent.parse_searches(
            await ai_provider.complete(provider, first, max_tokens=650), user
        )
        findings, steps = [], []
        for spec in searches:
            items = agent.search(db, user, spec)
            findings.extend(items)
            steps.append({"label": "Suche in " + (
                "Aufgaben" if spec["tool"] == "search_tasks"
                else "Anliegen" if spec["tool"] == "search_anliegen"
                else agent.modules.LABELS.get(spec["tool"], "Personen")
            ), "count": len(items)})
        categories = agent.categories_for(db, user)
        second = agent.plan_instructions(user, prompt, findings, categories, user.id)
        second[1:1] = context
        plan = agent.normalize_plan(
            await ai_provider.complete(provider, second, max_tokens=2200),
            user, findings, categories, db
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except ai_provider.AIProviderError as exc:
        raise HTTPException(502, "Der KI-Provider konnte den Arbeitsplan nicht erstellen.") from exc

    stash_put(request, "takt-agent-context", {"user_id": user.id, "prompts": [*prior, prompt][-3:]})
    # The actual commands remain server-side. A fresh plan invalidates the previous one.
    nonce = secrets.token_urlsafe(24) if plan["actions"] else ""
    stash_put(request, "takt-agent-plan", {
        "nonce": nonce, "user_id": user.id, "actions": plan["actions"],
    })
    return _response({
        "message": plan["message"],
        "steps": steps,
        "results": findings,
        "proposals": agent.preview(db, plan["actions"]),
        "plan_id": nonce,
    })


@app.post("/agent/cancel", dependencies=[Depends(check_csrf)])
def takt_agent_cancel(request: Request, plan_id: str = Form(...),
                      user: User = Depends(current_user)):
    _access(user)
    plan = stash_get(request, "takt-agent-plan", pop=True)
    if (not plan or not plan_id or not secrets.compare_digest(plan_id, plan.get("nonce", ""))
            or plan.get("user_id") != user.id):
        raise HTTPException(409, "Dieser Vorschlag ist nicht mehr gültig.")
    return _response({"cancelled": True})


@app.post("/agent/execute", dependencies=[Depends(check_csrf)])
def takt_agent_execute(request: Request, plan_id: str = Form(...),
                       user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    _access(user)
    rate_limit(request, "takt-agent-execute", limit=30, window=3600, key=str(user.id))
    # Pop first: a confirmation cannot be replayed, including after validation failures.
    plan = stash_get(request, "takt-agent-plan", pop=True)
    if (not plan or not plan_id or not secrets.compare_digest(plan_id, plan.get("nonce", ""))
            or plan.get("user_id") != user.id or not plan.get("actions")):
        raise HTTPException(409, "Der Vorschlag ist nicht mehr gültig. Bitte neu planen.")
    try:
        applied = agent.execute(db, user, plan["actions"])
    except Exception:
        db.rollback()
        raise
    return _response({"message": "Die freigegebenen Änderungen wurden gespeichert.",
                      "applied": applied})


@app.post("/agent/reset", dependencies=[Depends(check_csrf)])
def takt_agent_reset(request: Request, user: User = Depends(current_user)):
    _access(user)
    stash_get(request, "takt-agent-plan", pop=True)
    stash_get(request, "takt-agent-context", pop=True)
    return _response({"reset": True})
