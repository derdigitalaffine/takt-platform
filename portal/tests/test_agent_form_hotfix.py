import json
import re
from sqlalchemy import select
from app import ai_provider, agent
from app.db import SessionLocal, User, Form
from conftest import login, csrf_of, client
from test_agent_modules import isolated, fake, ADMIN


def test_agent_errors_are_json_even_with_default_fetch_accept(monkeypatch):
    c = login(*ADMIN); csrf = csrf_of(c.get('/').text)
    async def invalid(*args, **kwargs):
        return 'Kein JSON vom Modell'
    monkeypatch.setattr(ai_provider, 'complete', invalid)
    result = c.post('/agent/plan', data=dict(csrf=csrf, prompt='/takt Erstelle ein Formular'), headers={'Accept': '*/*'})
    # Invalid model JSON must not create a tool plan or produce a cryptic error.
    assert result.status_code == 200
    assert result.headers['content-type'].startswith('application/json')
    assert result.json()['proposals'] == []
    assert result.json()['plan_id'] == ''
    assert 'keinen sicheren TAKT-Vorschlag' in result.json()['message']
    assert result.headers['cache-control'] == 'no-store'
    assert c.post('/agent/plan', data=dict(prompt='/takt ja')).status_code == 400
    expired = client().post('/agent/plan', data=dict(prompt='/takt ja'))
    assert expired.headers['content-type'].startswith('application/json')
    assert expired.status_code in (400, 401)


def test_birthday_form_and_short_confirmation_open_real_closed_draft(monkeypatch):
    c = login(*ADMIN); csrf = csrf_of(c.get('/').text)
    fake(monkeypatch, [], [])
    response = c.post('/agent/plan', data=dict(csrf=csrf, prompt='/takt Erstelle ein Formular für die Geburtstage der Belegschaft'))
    assert response.status_code == 200
    proposal = dict(tool='create_form', title='Geburtstage der Belegschaft', fields=[
        dict(type='short', title='Name', required=True), dict(type='date', title='Geburtstag', required=False)])
    fake(monkeypatch, [], [proposal])
    response = c.post('/agent/plan', data=dict(csrf=csrf, prompt='/takt ja'))
    assert response.status_code == 200, response.text
    assert response.json()['open_url'].startswith('/forms?agent_plan=')
    assert 'Geburtstag' in response.json()['proposals'][0]
    pid = response.json()['plan_id']
    assert c.get(response.json()['open_url']).status_code == 200
    assert c.get('/agent/draft', params=dict(plan_id=pid)).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(Form).where(Form.title == proposal['title'])) is None
    review = c.post('/agent/draft/review', data=dict(csrf=csrf, agent_plan=pid, agent_step=0, title=proposal['title']))
    assert review.status_code == 200, review.text
    values = {k: re.search(r'name="' + k + r'" value="([^"]+)"', review.text).group(1) for k in ('csrf', 'plan_id', 'review_id')}
    assert c.post('/agent/draft/save', data=values).status_code == 303
    assert c.post('/agent/draft/save', data=values).status_code == 409
    with SessionLocal() as db:
        form = db.scalar(select(Form).where(Form.title == proposal['title']))
        assert form and form.internal and not form.active and form.public_token is None
        assert [f['title'] for f in json.loads(form.schema_json)] == ['Name', 'Geburtstag']


def test_form_creation_rechecks_role_and_rejects_process_or_executable_fields():
    import pytest
    from fastapi import HTTPException
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == ADMIN[0]))
        with pytest.raises(ValueError):
            agent.normalize_plan(json.dumps(dict(actions=[dict(tool='create_form', title='Testformular', fields=[dict(type='script', title='Nicht erlaubt')])])), u, [], [], db)
        from app.agent_forms import normalize
        from types import SimpleNamespace
        with pytest.raises(HTTPException):
            normalize(SimpleNamespace(active=True, can=lambda key: key == 'ai_chat'), dict(title='Nicht erlaubt', fields=[]))


def test_dock_is_independent_of_header_menu_and_same_origin_only():
    c = login(*ADMIN)
    page = c.get('/')
    assert 'data-agent-dock' in page.text and '/static/agent-dock.js' in page.text
    from html.parser import HTMLParser
    class Structure(HTMLParser):
        def __init__(self):
            super().__init__(); self.parents = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'a' and attrs.get('href') == '/agent':
                assert not any(p.get('id') == 'sidebar' for _, p in self.parents)
            if 'data-agent-dock' in attrs:
                assert not any(t == 'header' or 'app-topbar' in p.get('class', '') for t, p in self.parents)
            if tag not in ('meta', 'link', 'input', 'img', 'br', 'hr', 'source'):
                self.parents.append((tag, attrs))
        def handle_endtag(self, tag):
            for i in range(len(self.parents)-1, -1, -1):
                if self.parents[i][0] == tag:
                    del self.parents[i:]; break
    Structure().feed(page.text)
    panel = c.get('/agent?panel=1')
    assert panel.headers['x-frame-options'] == 'SAMEORIGIN'
    assert "frame-ancestors 'self'" in panel.headers['content-security-policy']
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']
