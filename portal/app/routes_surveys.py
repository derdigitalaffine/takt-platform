"""Unified navigation and creation; existing engines retain their protected endpoints."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from . import my_surveys, poll_lifecycle, survey_cockpit, surveys
from .db import User
from .main import app, current_user, enabled_modules, get_db, redirect, render


def _modules():
    modules = enabled_modules()
    if 'polls' not in modules:
        raise HTTPException(404, 'Umfragen sind auf diesem Server nicht eingeschaltet.')
    return modules


@app.get('/teilnahme-cockpit')
def participation_cockpit(request: Request, q: str = '', kind: str = 'all',
                          state: str = 'all',
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cross-engine manager dashboard. No raw or personal answer data."""
    modules = enabled_modules()
    if not modules.intersection({'forms', 'polls'}):
        raise HTTPException(404, 'Keine Umfragen aktiviert.')
    entries = survey_cockpit.collect(db, user, modules)
    kind = kind if kind in ('all', *survey_cockpit.KINDS) else 'all'
    state = state if state in ('all', 'active', 'archived') else 'all'
    q = q.strip()[:160]
    rows = [r for r in entries if (kind == 'all' or r['kind'] == kind)
            and (state == 'all' or (r['status'] == 'Archiviert') == (state == 'archived'))
            and (not q or q.casefold() in (r['title'] + ' ' + r['description']).casefold())]
    response = render(request, 'survey_cockpit.html', user, rows=rows,
                      totals=survey_cockpit.totals(rows), kind=kind, state=state, q=q,
                      kinds=survey_cockpit.KINDS,
                      forms_enabled='forms' in modules, polls_enabled='polls' in modules,
                      can_manage=_can_manage(db, user, modules))
    response.headers['Cache-Control'] = 'no-store'
    return response


def _can_manage(db: Session, user: User, modules: set[str]) -> bool:
    """Make the manager tab available only when users can actually manage surveys."""
    if 'polls' not in modules:
        return False
    if user.is_admin or surveys.available(user, modules):
        return True
    return bool(surveys.collect(db, user, modules, state='active') or
                surveys.collect(db, user, modules, state='archive'))


@app.get('/meine-umfragen')
def my_surveys_page(request: Request, q: str = '', status: str = 'all', kind: str = 'all',
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Personal participation is accessible without poll-editor permissions."""
    modules = enabled_modules()
    if not modules.intersection({'forms', 'polls'}):
        raise HTTPException(404, 'Umfragen sind auf diesem Server nicht eingeschaltet.')
    entries = my_surveys.collect(db, user, modules)
    totals = my_surveys.summary(entries)
    status = status if status in ('all', 'open', 'done', 'closed') else 'all'
    kind = kind if kind in ('all', 'form', 'poll', 'vote') else 'all'
    q = q.strip()[:160]
    rows = [row for row in entries if (status == 'all' or row['status'] == status)
            and (kind == 'all' or row['kind'] == kind)
            and (not q or q.casefold() in (row['title'] + ' ' + row['description']).casefold())]
    response = render(request, 'my_surveys.html', user, rows=rows, totals=totals,
                      status=status, kind=kind, q=q,
                      forms_enabled='forms' in modules, polls_enabled='polls' in modules)
    response.headers['Cache-Control'] = 'no-store'
    return response



@app.get('/umfragen')
def survey_list(request: Request, q: str = '', kind: str = '', state: str = 'active', scope: str = 'all',
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    modules = _modules()
    if not _can_manage(db, user, modules):
        return redirect('/meine-umfragen')
    q = q.strip()[:200]
    kind = kind if kind in surveys.KINDS else ''
    state = state if state in ('active', 'archive', 'trash') else 'active'
    scope = scope if scope in ('own', 'shared', 'all', 'portal') else 'all'
    if scope == 'portal' and not user.is_admin:
        scope = 'all'
    rows = surveys.collect(db, user, modules, state=state, scope=scope, admin_all=scope == 'portal') if state != 'trash' else []
    totals = {key: sum(row['kind'] == key for row in rows) for key in surveys.KINDS}
    rows = [row for row in rows if (not kind or row['kind'] == kind)
            and (not q or q.casefold() in (row['title'] + ' ' + row['description'] + ' ' + row['owner']).casefold())]
    trash = []
    if state == 'trash':
        if 'polls' in modules:
            for item in poll_lifecycle.trash_items(db, ['poll', 'vote', 'live_poll'], user):
                item_kind = {'poll': 'poll', 'vote': 'vote', 'live_poll': 'live'}[item.kind]
                if (not kind or kind == item_kind) and (not q or q.casefold() in item.label.casefold()) and scope != 'shared' and (scope == 'portal' or poll_lifecycle.trash_owner(item) == user.id):
                    trash.append(dict(title=item.label, kind=item_kind, expires=item.expires_at,
                                      restore=f'/umfragen/papierkorb/{item.id}/restore'))
    return render(request, 'surveys.html', user, rows=rows, trash=trash, kinds=surveys.KINDS,
                  create_kinds=surveys.available(user, modules), q=q, kind=kind, state=state, scope=scope, totals=totals,
                  survey_url=lambda **overrides: surveys.url(**{'q': q, 'kind': kind, 'state': state, 'scope': scope, **overrides}))


@app.get('/umfragen/neu')
def survey_new(request: Request, user: User = Depends(current_user)):
    choices = surveys.available(user, _modules())
    if not choices:
        raise HTTPException(403, 'Zum Anlegen einer Umfrage fehlt die Berechtigung.')
    return render(request, 'survey_new.html', user, kinds=surveys.KINDS, choices=choices)
