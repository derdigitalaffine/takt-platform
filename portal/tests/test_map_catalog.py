"""Catalog discovery, explicit selection and permission-safe repeat imports."""
import json

import httpx
import pytest
from sqlalchemy import select

from app import map_catalog, maps
from app.db import MapLayer
from conftest import client, csrf_of, login
from test_circulations import actors


@pytest.fixture
def manager(db, actors):
    actors[0].permissions += ',maps_admin'
    db.commit()
    return login(actors[0].email, 'passwort-test-123')


@pytest.fixture
def service(monkeypatch):
    result = {'type': 'wms', 'url': 'https://example.org/library-test', 'version': '1.3.0',
              'title': 'Testdienst', 'layers': [
                  {'name': 'a', 'title': 'Erste Ebene', 'supported': True, 'queryable': True,
                   'service': {'info_format': 'application/json'}, 'times': ['2025','2026'], 'time': '2026', 'legend': 'https://example.org/legend'},
                  {'name': 'b', 'title': 'Zweite Ebene', 'supported': True},
                  {'name': 'c', 'title': 'Nicht unterstützt', 'supported': False}]}
    monkeypatch.setattr(maps, 'query_service', lambda *args: result)
    return result


def test_catalog_metadata_and_filters():
    assert len(map_catalog.CATALOG) >= 40
    for key, spec in map_catalog.CATALOG.items():
        assert spec['url'].startswith('https://')
        assert all(spec[field] for field in ('region','topic','provider','license','license_url','source_url','attribution'))
    assert map_catalog.search('luftBILDer', 'Sachsen')
    assert not map_catalog.search('zz-no-source')
    assert all(s['topic']=='Kataster' for s in map_catalog.search(topic='Kataster').values())


def test_library_requires_admin_and_csrf(manager, db, actors, monkeypatch):
    monkeypatch.setattr(maps, 'query_service', lambda *a: pytest.fail('unauthorized discovery'))
    guest = client()
    for c in [guest, login(actors[1].email, 'passwort-test-123')]:
        token = csrf_of(c.get('/login').text)
        assert c.post('/admin/maps/library/de-basemap', data={'csrf':token}).status_code in (303,401,403)
        assert c.post('/admin/maps/library/de-basemap/import', data={'csrf':token,'layers':'a'}).status_code in (303,401,403)
    assert manager.post('/admin/maps/library/de-basemap').status_code == 400


def test_library_filter_and_preview(manager, service):
    page = manager.get('/admin/maps?q=luftbilder&region=Sachsen')
    assert page.status_code == 200 and 'Kartenbibliothek Deutschland' in page.text
    assert '/library/sn-dop-rgb' in page.text and '/library/de-basemap' not in page.text
    token = csrf_of(page.text)
    preview = manager.post('/admin/maps/library/de-basemap', data={'csrf':token})
    assert preview.status_code == 200 and 'Erste Ebene' in preview.text and 'Zweite Ebene' in preview.text
    assert 'Nicht unterstützt' not in preview.text
    assert manager.post('/admin/maps/library/missing', data={'csrf':token}).status_code == 404


def test_selected_import_is_private_inactive_and_repeatable(manager, service, db):
    token = csrf_of(manager.get('/admin/maps').text)
    original = MapLayer(name='Original', kind='wms', url='https://example.org/original', role='base', default_visible=True, enabled=True, public=True)
    db.add(original); db.commit()
    try:
        for _ in range(2):
            r=manager.post('/admin/maps/library/de-basemap/import', data={'csrf':token,'layers':['a','b','a']})
            assert r.status_code == 303
        db.expire_all()
        rows=list(db.scalars(select(MapLayer).where(MapLayer.url==service['url'])))
        assert len(rows)==2
        assert {r.layers for r in rows}=={'a','b'}
        assert all(not r.enabled and not r.public and not r.default_visible and not r.in_forms and r.proxy and r.role=='base' for r in rows)
        a=next(r for r in rows if r.layers=='a')
        assert json.loads(a.service_json)['info_format']=='application/json'
        assert a.time_values=='2025,2026' and a.time_default=='2026' and a.feature_info
        assert a.legend_url.endswith('/legend') and map_catalog.CATALOG['de-basemap']['license_url'] in a.description
        assert original.default_visible and original.enabled and original.public
    finally:
        db.query(MapLayer).filter(MapLayer.url==service['url']).delete()
        db.delete(original);db.commit()


@pytest.mark.parametrize('names', [[], ['a','c'], ['a','unknown'], [str(i) for i in range(101)]])
def test_invalid_selection_imports_nothing(manager, service, db, names):
    token = csrf_of(manager.get('/admin/maps').text)
    r=manager.post('/admin/maps/library/de-basemap/import', data={'csrf':token,'layers':names})
    assert r.status_code==303
    assert not db.scalar(select(MapLayer).where(MapLayer.url==service['url']))


def test_catalog_source_scope_and_failure(manager, service, monkeypatch, db):
    assert map_catalog.choices({'layer':'b'},service)==[service['layers'][1]]
    monkeypatch.setattr(maps,'query_service',lambda *a: (_ for _ in ()).throw(httpx.ConnectTimeout('unavailable')))
    token=csrf_of(manager.get('/admin/maps').text)
    for suffix in ['', '/import']:
        r=manager.post('/admin/maps/library/de-basemap'+suffix,data={'csrf':token,'layers':'a'})
        assert r.status_code==200 and 'Quelle derzeit nicht verfügbar' in r.text
        if suffix:
            assert 'value="a" checked' in r.text
        else:
            assert 'Quelle erneut abfragen' in r.text
    assert not db.scalar(select(MapLayer).where(MapLayer.url==service['url']))
