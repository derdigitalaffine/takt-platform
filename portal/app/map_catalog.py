"""Curated public services. Discover layer names live; never guess a provider's first layer.

Source links document availability and terms. No remote requests run on the settings page.
Keep this catalog separate from the RLP parcel lookup (which has its own data model).
"""
from datetime import datetime, timezone

from . import parcels

YEAR = datetime.now(timezone.utc).year
BY = 'https://www.govdata.de/dl-de/by-2-0'
ZERO = 'https://www.govdata.de/dl-de/zero-2-0'
CC = 'https://creativecommons.org/licenses/by/4.0/'


def source(name, url, region, topic, provider, source_url, license, license_url,
           *, role='overlay', layer='', note='', attribution=''):
    return dict(name=name, url=url, region=region, topic=topic, provider=provider,
                source_url=source_url, license=license, license_url=license_url,
                role=role, layer=layer, kind='wms', note=note,
                attribution=attribution or f'© {provider} ({YEAR}), {license}; {license_url}')


CATALOG = {}


def add(key, *args, **kwargs):
    CATALOG[key] = source(*args, **kwargs)


BKG = 'https://gdz.bkg.bund.de/index.php/default/'
add('de-topplus', 'TopPlusOpen – Farbe und Grau', 'https://sgx.geodatenzentrum.de/wms_topplus_open',
    'Deutschland', 'Grundkarten', 'BKG', BKG+'wms-topplusopen-wms-topplus-open.html', 'DL-DE BY 2.0', BY, role='base',
    attribution=f'© BKG ({YEAR}) <a href="{BY}">dl-de/by-2-0</a>, <a href="https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_topplusopen.html">Datenquellen</a>; <a href="https://www.bkg.bund.de">BKG</a>')
add('de-basemap', 'basemap.de – amtliche Webkarte', 'https://sgx.geodatenzentrum.de/wms_basemapde',
    'Deutschland', 'Grundkarten', 'GeoBasis-DE / BKG', BKG+'wms-basemapde-webraster-wms-basemapde-webraster.html', 'CC BY 4.0', CC, role='base',
    attribution=f'© GeoBasis-DE / <a href="https://www.bkg.bund.de">BKG</a> ({YEAR}) <a href="{CC}">CC BY 4.0</a>')
add('de-relief', 'basemap.de – Relief und Schummerung', 'https://sgx.geodatenzentrum.de/wms_basemapde_schummerung',
    'Deutschland', 'Gelände', 'GeoBasis-DE / BKG', 'https://basemap.de/dienste/', 'CC BY 4.0', CC)
add('de-bfn', 'Schutzgebiete in Deutschland', 'https://geodienste.bfn.de/ogc/wms/schutzgebiet',
    'Deutschland', 'Natur und Umwelt', 'Bundesamt für Naturschutz (BfN)', 'https://www.bfn.de/schutzgebiete',
    'GeoNutzV', 'https://www.gesetze-im-internet.de/geonutzv/', note='Übersichtsdaten; laut Anbieter nicht für Planungszwecke geeignet.')
add('de-dwd', 'Wetter – Warnungen, Radar und Vorhersage', 'https://maps.dwd.de/geoserver/ows',
    'Deutschland', 'Wetter und Klima', 'Deutscher Wetterdienst (DWD)',
    'https://www.dwd.de/DE/leistungen/geodaten/Geodaten.html', 'GeoNutzV / DWD',
    'https://www.wettergefahren.de/vorlagen_quellenangabe.html', note='Zeit und Aktualität unterscheiden sich je Ebene.')
add('de-dwd-climate', 'Klima – Climate Data Center', 'https://cdc.dwd.de/geoserver/ows',
    'Deutschland', 'Wetter und Klima', 'Deutscher Wetterdienst (DWD)', 'https://cdc.dwd.de/geoserver/web/',
    'GeoNutzV / DWD', 'https://www.wettergefahren.de/vorlagen_quellenangabe.html')
CATALOG['de-dwd']['layer_prefix'] = 'dwd:'
CATALOG['de-dwd-climate']['exclude_layers'] = ['BKG_VG1000_LAN_DWD']

NRW = 'https://www.bezreg-koeln.nrw.de/geobasis-nrw'
for key, title, service, topic, role in [
    ('dop', 'Luftbilder', 'dop', 'Luftbilder', 'base'),
    ('alkis', 'Liegenschaftskarte – Farbe', 'alkis', 'Kataster', 'overlay'),
    ('alkis-gray', 'Liegenschaftskarte – Grau', 'alkis_grau', 'Kataster', 'overlay'),
    ('alkis-yellow', 'Liegenschaftskarte – Gelb', 'alkis_gelb', 'Kataster', 'overlay'),
    ('abk', 'Amtliche Basiskarte', 'abk', 'Grundkarten', 'base'),
    ('dtk', 'Topographische Karten', 'dtk', 'Grundkarten', 'base'),
    ('parcels', 'INSPIRE Flurstücke', 'inspire-flurstuecke_alkis', 'Kataster', 'overlay'),
]:
    add('nw-'+key, 'NRW – '+title, 'https://www.wms.nrw.de/geobasis/wms_nw_'+service,
        'Nordrhein-Westfalen', topic, 'Land NRW / Geobasis NRW', NRW, 'DL-DE ZERO 2.0', ZERO, role=role)

BAVARIA = 'https://geodaten.bayern.de/opengeodata/'
for service, title in [('dok', 'Ortskarte'), ('dtk25', 'Topographie 1:25.000'),
                       ('dtk50', 'Topographie 1:50.000'), ('dtk100', 'Topographie 1:100.000'),
                       ('dtk500', 'Topographie 1:500.000')]:
    add('by-'+service, 'Bayern – '+title, 'https://geoservices.bayern.de/od/wms/dtk/v1/'+service,
        'Bayern', 'Grundkarten', 'Bayerische Vermessungsverwaltung', BAVARIA, 'CC BY 4.0', CC, role='base')
for key, title, service in [('dop', 'Luftbilder DOP20', 'dop/v1/dop20'),
                             ('histdop', 'Historische Luftbilder', 'histdop/v1/histdop')]:
    add('by-'+key, 'Bayern – '+title, 'https://geoservices.bayern.de/od/wms/'+service,
        'Bayern', 'Luftbilder', 'Bayerische Vermessungsverwaltung', BAVARIA, 'CC BY 4.0', CC, role='base')
add('by-nature', 'Bayern – Schutzgebiete', 'https://www.lfu.bayern.de/gdi/wms/natur/schutzgebiete',
    'Bayern', 'Natur und Umwelt', 'Bayerisches Landesamt für Umwelt',
    'https://www.lfu.bayern.de/umweltdaten/geodatendienste/index_detail.htm?id=1e025cc4-d4b1-378e-9924-45950aef2334&profil=WMS',
    'CC BY 4.0', CC, note='Rechtsverbindliche Grenzen bei der zuständigen Naturschutzbehörde einsehen.',
    attribution=f'Datenquelle: Bayerisches Landesamt für Umwelt, www.lfu.bayern.de, CC BY 4.0 ({CC})')

for key, title, service, topic, role in [
    ('dop', 'Luftbilder Farbe', 'dop20c', 'Luftbilder', 'base'),
    ('cir', 'Luftbilder Infrarot', 'dop20cir', 'Luftbilder', 'base'),
    ('dgm', 'Digitales Geländemodell', 'dgm', 'Gelände', 'overlay'),
]:
    add('bb-'+key, 'Brandenburg / Berlin – '+title, 'https://isk.geobasis-bb.de/mapproxy/'+service+'/service/wms',
        'Brandenburg / Berlin', topic, 'GeoBasis-DE / LGB', 'https://geobasis-bb.de/lgb/de/geodaten/geodienste/',
        'DL-DE BY 2.0', BY, role=role,
        attribution=f'© GeoBasis-DE/LGB, dl-de/by-2-0 ({BY}); für Berlin: © GeoBasis-DE / SenStadt')

HE = 'https://www.geoportal.hessen.de/article/Kartenebenen/'
for key, title, path, topic, role in [
    ('dop', 'Luftbilder', 'lika-services/ogc-free-images.ows', 'Luftbilder', 'base'),
    ('borders', 'Verwaltungseinheiten und Gemarkungen', 'verweinh/he-verwaltungseinheiten.ows', 'Grenzen', 'overlay'),
]:
    add('he-'+key, 'Hessen – '+title, 'https://www.gds-srv.hessen.de/cgi-bin/'+path,
        'Hessen', topic, 'Hessische Verwaltung für Bodenmanagement und Geoinformation', HE,
        'Kostenfreie Nutzung nach HVGG', 'https://hvbg.hessen.de/open-data', role=role)

for suffix, title in [('rgb', 'Farbe'), ('cir', 'Infrarot'), ('pan', 'Grau')]:
    add('sn-dop-'+suffix, 'Sachsen – Luftbilder '+title, 'https://geodienste.sachsen.de/wms_geosn_dop-'+suffix+'/guest',
        'Sachsen', 'Luftbilder', 'Geodaten Sachsen', 'https://www.landesvermessung.sachsen.de/luftbild-produkte-4982.html',
        'DL-DE BY 2.0', BY, role='base')
add('th-dop', 'Thüringen – Luftbilder', 'https://www.geoproxy.geoportal-th.de/geoproxy/services/DOP',
    'Thüringen', 'Luftbilder', 'GeoBasis-DE / GDI-Th',
    'https://geoportal.geoportal-th.de/gaialight-th/_apps/dladownload/dl-lbop-info.html', 'CC BY 4.0', CC, role='base',
    attribution=f'© GDI-Th, CC BY 4.0 ({CC})')

for key, title, path, topic in [
    ('soil', 'Bodenübersichtskarte 1:200.000', 'boden/buek200', 'Boden und Geologie'),
    ('geology', 'Geologische Übersicht 1:2.750.000', 'geologie/gk2750', 'Boden und Geologie'),
]:
    add('de-'+key, title, 'https://services.bgr.de/wms/'+path+'/', 'Deutschland', topic,
        'Bundesanstalt für Geowissenschaften und Rohstoffe (BGR)', 'https://geoviewer.bgr.de/',
        'GeoNutzV', 'https://www.bgr.bund.de/agb', note='Übersichtskarte; Maßstab und Datenstand beim Einsatz beachten.')
CATALOG['de-soil']['attribution'] = 'Datenquelle: BÜK200, © BGR, Hannover, 2018; https://www.bgr.bund.de/agb'

# Preserve the established keys and exact layer constraints of the existing RLP sources.
for key, spec in parcels.CATALOG.items():
    CATALOG['rp-'+key] = dict(spec, region='Rheinland-Pfalz',
        topic='Bauleitplanung' if key.startswith('plans-') else ('Grenzen' if key=='boundaries' else 'Kataster' if key in ('lika','lika-info','parcels') else 'Grundkarten'),
        provider='Kommunaler Herausgeber / GeoPortal RLP' if key.startswith('plans-') else 'LVermGeo Rheinland-Pfalz',
        source_url='https://www.geoportal.rlp.de/',
        license='Nutzungsbedingungen des Herausgebers' if key.startswith('plans-') else 'DL-DE BY 2.0',
        license_url='https://www.geoportal.rlp.de/' if key.startswith('plans-') else BY,
        attribution=spec.get('attribution', parcels.ATTRIBUTION), kind=spec.get('kind','wms'),
        role='base' if key.startswith('dtk') else 'overlay', note='')


def search(query='', region='', topic=''):
    words = query.casefold().split()
    return {key: item for key, item in CATALOG.items()
            if (not region or region == item['region']) and (not topic or topic == item['topic'])
            and all(word in ' '.join(str(v) for v in item.values()).casefold() for word in words)}


def choices(spec, result):
    """Only return explicitly supported, named layers within a catalog entry's scope."""
    return [layer for layer in result['layers'] if layer.get('name') and layer.get('supported', True)
            and layer['name'].startswith(spec.get('layer_prefix', ''))
            and layer['name'] not in spec.get('exclude_layers', [])
            and (not spec.get('layer') or layer['name'] == spec['layer'])]
