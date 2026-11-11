"""Spatial law references must never turn an internal card or attachment public."""
import json
import secrets

import pytest
from sqlalchemy import select

from app import law_maps, laws, maps
from app.db import LawAttachment, LawText, LawVersion, UserMap
from conftest import client, csrf_of, login, settings
from test_circulations import actors


AREA={'type':'Polygon','coordinates':[[[7.76,49.49],[7.78,49.49],[7.78,49.5],[7.76,49.49]]]}


@pytest.fixture
def plan(db, actors):
    settings(module_laws='1',module_maps='1')
    actors[0].permissions+=',laws'
    law=LawText(title='Plan am Bach',slug='plan-'+secrets.token_hex(4),body_md='# Plan\n\n### § 1 Geltungsbereich\nText',published=True)
    db.add(law);db.flush()
    card=UserMap(title='Interne Fachkarte',owner_id=actors[0].id,state_json=json.dumps({'drawings':[{'type':'Feature','geometry':{'type':'Point','coordinates':[7.77,49.49]},'properties':{'name':'INTERNES OBJEKT'}}]}))
    attachment=LawAttachment(law_id=law.id,name='INTERNES PDF',file='private-test.pdf',internal=True)
    db.add_all([card,attachment]);db.commit()
    c=login(actors[0].email,'passwort-test-123')
    yield law,card,attachment,c,actors
    db.query(LawVersion).filter(LawVersion.law_id==law.id).delete()
    db.delete(attachment);db.delete(law);db.delete(card);db.commit()


def payload(law,card,attachment):
    return {'map_id':str(card.id),'attachment_id':str(attachment.id),'geometry':json.dumps(AREA)}


def test_save_view_and_public_isolation(db,plan):
    law,card,attachment,c,_=plan
    page=c.get(f'/laws/{law.id}/map');assert page.status_code==200
    data=payload(law,card,attachment);data['csrf']=csrf_of(page.text)
    assert c.post(f'/laws/{law.id}/map',data=data).status_code==303
    db.refresh(law)
    assert law_maps.state(law)['geometry']==AREA
    public=client().get(f'/karte/recht/{law.id}')
    assert public.status_code==200 and 'Plan am Bach' in public.text
    assert 'INTERNES OBJEKT' not in public.text and 'INTERNES PDF' not in public.text
    assert 'INTERNES OBJEKT' in c.get(f'/karte/recht/{law.id}').text
    assert f'/karte/recht/{law.id}' in client().get(f'/recht/{law.slug}').text
    card.public_token=secrets.token_urlsafe(16);db.commit()
    assert 'INTERNES OBJEKT' in client().get(f'/karte/recht/{law.id}').text
    card.public_token=None;db.commit()
    assert 'INTERNES OBJEKT' not in client().get(f'/karte/recht/{law.id}').text
    law.published=False;db.commit()
    assert client().get(f'/karte/recht/{law.id}').status_code==404
    assert c.get(f'/karte/recht/{law.id}').status_code==200


def test_versions_keep_boundary_and_access(db,plan):
    law,card,attachment,c,_=plan
    law.map_json=json.dumps({'geometry':AREA})
    laws.snapshot(db,law,public=True,valid_until='2026-10-01');db.flush()
    version=db.scalar(select(LawVersion).where(LawVersion.law_id==law.id))
    law.map_json='{}';db.commit()
    assert client().get(f'/karte/recht/{law.id}').status_code==404
    response=client().get(f'/karte/recht/{law.id}?version={version.id}')
    assert response.status_code==200 and f'/fassung/{version.id}' in response.text
    assert f'?version={version.id}' in client().get(f'/recht/{law.slug}/fassung/{version.id}').text
    version.internal=True;db.commit()
    assert client().get(f'/karte/recht/{law.id}?version={version.id}').status_code==404
    assert c.get(f'/karte/recht/{law.id}?version={version.id}').status_code==200


def test_no_bypass_through_foreign_map_or_attachment(db,plan):
    law,card,attachment,c,people=plan
    token=csrf_of(c.get(f'/laws/{law.id}/map').text)
    outsider=login(people[1].email,'passwort-test-123')
    assert outsider.get(f'/laws/{law.id}/map').status_code==403
    assert c.post(f'/laws/{law.id}/map',data=payload(law,card,attachment)).status_code==400
    card.owner_id=people[1].id;db.commit()
    response=c.post(f'/laws/{law.id}/map',data={**payload(law,card,attachment),'csrf':token})
    assert response.status_code==200 and 'nicht zugänglich' in response.text
    db.refresh(law);assert law.map_json=='{}'
    with pytest.raises(ValueError):law_maps.clean(db,law,people[0],{'geometry':'{"type":"Point","coordinates":[7,49]}'})
    with pytest.raises(ValueError):law_maps.clean(db,law,people[0],{'attachment_id':str(attachment.id)})


def test_internal_only_card_cannot_open_anonymous_map(db,plan):
    law,card,attachment,c,_=plan
    law.map_json=json.dumps({'map_id':card.id});db.commit()
    assert client().get(f'/karte/recht/{law.id}').status_code==404
    assert 'Auf Karte anzeigen' not in client().get(f'/recht/{law.slug}').text
    assert c.get(f'/karte/recht/{law.id}').status_code==200


def test_circle_radius_derived_from_geometry_and_text_preserved():
    # Opposite points 0.002 degrees apart: radius about 111 m, regardless of supplied metadata.
    geometry={'type':'Polygon','coordinates':[[[-.001,0],[0,.001],[.001,0],[0,-.001],[-.001,0]]]}
    clean=maps.clean_drawings([{'geometry':geometry,'properties':{'shape':'circle','radius_m':999999,'name':'Kreis'}}])[0]
    assert clean['properties']['shape']=='circle'
    assert 110<clean['properties']['radius_m']<112
    text=maps.clean_drawings([{'geometry':{'type':'Point','coordinates':[7,49]},'properties':{'shape':'text','name':'Plan A'}}])[0]
    assert text['properties']['shape']=='text' and text['properties']['name']=='Plan A'
