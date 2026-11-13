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
           *, role='overlay', layer='', note='', attribution='', kind='wms',
           tile_size=256, maxzoom=19):
    return dict(name=name, url=url, region=region, topic=topic, provider=provider,
                source_url=source_url, license=license, license_url=license_url,
                role=role, layer=layer, kind=kind, note=note,
                tile_size=tile_size, maxzoom=maxzoom,
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



# Official LVermGeo RP source URLs below are the GetCapabilities links
# published in the Open Data service directory. We discover the supported
# layer names lazily; never assume a particular WMS layer still exists.
RLP_OPEN = 'https://lvermgeo.rlp.de/geodaten-geoshop/open-data/'
RLP_WMS = 'https://www.geoportal.rlp.de/mapbender/php/wms.php?layer_id={id}&withChilds=1'
RLP_ATTR = f'©GeoBasis-DE / LVermGeoRP {YEAR}, dl-de/by-2-0, www.lvermgeo.rlp.de'
for key, title, layer_id, topic, role in [
    ('dop20', 'RP · Digitale Orthophotos (20 cm)', 61675, 'Luftbilder', 'base'),
    ('dop-historic', 'RP · Historische Luftbilder (Zeitauswahl)', 74200, 'Luftbilder', 'overlay'),
    ('relief1', 'RP · Schummerung (1 m)', 49358, 'Gelände', 'overlay'),
    ('contours', 'RP · Höhenlinien', 32876, 'Gelände', 'overlay'),
    ('soil-estimate', 'RP · Bodenschätzung tagesaktuell', 86762, 'Boden und Geologie', 'overlay'),
]:
    add('rp-'+key, title, RLP_WMS.format(id=layer_id),
        'Rheinland-Pfalz', topic, 'LVermGeo Rheinland-Pfalz',
        RLP_OPEN, 'DL-DE BY 2.0', BY, role=role,
        note='Dienst und angebotene Layer werden erst bei Auswahl geprüft. '
             'Maßstab, Aktualität und Nutzbarkeit beachten.',
        attribution=RLP_ATTR)

# Further official free data sources, taken from the LVermGeo Open Data
# Capabilities links. These are curated *service* URLs rather than private
# cadastral records; the actual advertised feature names are fetched lazily.
for key, title, layer_id, topic in [
    ('afis-fixedpoints', 'RP · AFIS Festpunktübersicht', 76140, 'Vermessung'),
    ('properties-wms', 'RP · Liegenschaften (Übersicht)', 61680, 'Kataster'),
]:
    add('rp-'+key, title, RLP_WMS.format(id=layer_id),
        'Rheinland-Pfalz', topic, 'LVermGeo Rheinland-Pfalz',
        RLP_OPEN, 'DL-DE BY 2.0', BY,
        note='Amtliche Darstellungsdaten. Aktualität, Maßstab, '
             'Datenumfang und Eignung für den Einsatzzweck prüfen.',
        attribution=RLP_ATTR)

for key, title, endpoint, topic in [
    ('alkis-points-wfs', 'RP · ALKIS-Punkte (WFS)',
     'https://www.geoportal.rlp.de/registry/wfs/669', 'Kataster'),
    ('alkis-simplified-wfs', 'RP · ALKIS vereinfacht (WFS)',
     'https://www.geoportal.rlp.de/registry/wfs/519', 'Kataster'),
    ('soil-wfs', 'RP · Bodenschätzung (WFS)',
     'https://www.geoportal.rlp.de/registry/wfs/571', 'Boden und Geologie'),
]:
    add('rp-'+key, title, endpoint, 'Rheinland-Pfalz',
        topic, 'LVermGeo Rheinland-Pfalz', RLP_OPEN,
        'DL-DE BY 2.0', BY, kind='wfs',
        note='Die amtliche WFS-Schnittstelle und angebotene Geometrien '
             'werden erst beim Öffnen geprüft. Große Datenmengen sowie '
             'nicht unterstützte Koordinatenreferenzsysteme erfordern '
             'die Nutzung des offiziellen Downloadangebotes.',
        attribution=RLP_ATTR)

# Landesfachdaten beyond cadastral/topographic data. The original
# licensing is different: do not relabel third-party sectoral data
# under the LVermGeo data licence.
for key, title, lid, topic in [
    ('flood-hq100', 'RP · Hochwassergefahr – Wassertiefe HQ100', 73097, 'Wasser und Hochwasser'),
    ('flood-extreme', 'RP · Hochwassergefahr – Wassertiefe Extrem', 70256, 'Wasser und Hochwasser'),
    ('flood-rivers', 'RP · Hochwasserrisikogewässer (Stand 2018)', 86507, 'Wasser und Hochwasser'),
]:
    add('rp-'+key, title, RLP_WMS.format(id=lid), 'Rheinland-Pfalz',
        topic, 'Wasserwirtschaftsverwaltung Rheinland-Pfalz',
        'https://www.geoportal.rlp.de/', 'CC BY 4.0', CC,
        note='Fachdaten mit Anbieterzeitstand; keine Echtzeitvorhersage und '
             'kein Ersatz für amtliche Warnungen oder Gefahrenbeurteilung.',
        attribution=f'© Wasserwirtschaftsverwaltung Rheinland-Pfalz ({YEAR}), CC BY 4.0')
add('rp-nature-reserves', 'RP · Naturschutzgebiete',
    RLP_WMS.format(id=30825), 'Rheinland-Pfalz', 'Natur und Umwelt',
    'Naturschutzverwaltung Rheinland-Pfalz (LANIS)',
    'https://www.geoportal.rlp.de/', 'ODbL 1.0',
    'https://opendatacommons.org/licenses/odbl/1-0/',
    note='Schutzgebietsdaten zum Überblick; für verbindliche Grenzen '
         'sind die amtlichen Rechtsgrundlagen maßgeblich.',
    attribution='Daten © Naturschutzverwaltung Rheinland-Pfalz (LANIS), ODbL 1.0')

add('rp-atkis-basis', 'RP · ATKIS Basis-DLM – Objekte',
    'https://geo5.service24.rlp.de/wfs/basisdlm_shape_rp.fcgi', 'Rheinland-Pfalz',
    'Topografie', 'LVermGeo Rheinland-Pfalz', RLP_OPEN,
    'DL-DE BY 2.0', BY, kind='wfs',
    note='Nur unterstützte WFS-Featuretypen mit begrenztem Kartenausschnitt; '
         'größere Datenmengen beim Anbieter herunterladen.', attribution=RLP_ATTR)

# OpenRailwayMap supplies transparent overlays, not a standalone street map.
# The volunteer-hosted service has strict fair-use terms. Nothing is fetched
# until the user deliberately enables the layer; never precache in bulk.
ORM_LICENSE = 'https://wiki.openstreetmap.org/wiki/DE:OpenRailwayMap/API'
ORM_ATTR = ('Daten © OpenStreetMap-Mitwirkende, '
            'Grafik CC-BY-SA 2.0 © OpenRailwayMap')
for style, label in [
    ('standard', 'Bahninfrastruktur und Gleise'),
    ('signals', 'Signale und Zugsicherung'),
    ('maxspeed', 'Streckenhöchstgeschwindigkeiten'),
    ('electrification', 'Elektrifizierung'),
    ('gauge', 'Spurweiten'),
]:
    add('orm-'+style, 'OpenRailwayMap · '+label,
        'https://tiles.openrailwaymap.org/'+style+'/{z}/{x}/{y}.png',
        'Weltweit', 'Eisenbahn', 'OpenRailwayMap / OpenStreetMap',
        'https://www.openrailwaymap.org/', 'CC BY-SA 2.0 / ODbL',
        ORM_LICENSE, kind='xyz', tile_size=512, maxzoom=18,
        note='Ehrenamtlicher Best-Effort-Dienst: keine Massenabfragen, nur '
             'bei aktivem Layer laden; nur für öffentlich zugängliche '
             'Anwendungen ohne Registrierungspflicht.',
        attribution=ORM_ATTR)

# Not every free GIS product is a ready-made tile or WMS service.
# In particular CityGML LoD1/LoD2 must be downloaded and converted to a
# suitable streaming format before it can be rendered in MapLibre.
DATASETS = {
    'rp-lod1': {
        'name': 'RP · 3D-Gebäudemodell LoD1 (Blockmodell)',
        'topic': '3D-Gebäude', 'region': 'Rheinland-Pfalz',
        'provider': 'LVermGeo Rheinland-Pfalz',
        'source_url': 'https://lvermgeo.rlp.de/produktinformationen/geotopografie/3d-geodaten/3d-gebaeudemodell',
        'download_url': 'https://geoshop.rlp.de/id-3d-gebaeudemodelle/_3d-gebaeudemodelle.html',
        'viewer_url': 'https://rlp.plexmap.de/v/RLP-in-3D-neu/',
        'license': 'DL-DE BY 2.0', 'license_url': BY,
        'format': 'CityGML', 'kind': 'download',
        'note': 'Amtliches LoD1: Gebäude als Blockmodell mit Flachdach. '
                'Keine unmittelbar streambaren MapLibre-Kacheln veröffentlicht.'
    },
    'rp-lod2': {
        'name': 'RP · 3D-Gebäudemodell LoD2 (Dachformen)',
        'topic': '3D-Gebäude', 'region': 'Rheinland-Pfalz',
        'provider': 'LVermGeo Rheinland-Pfalz',
        'source_url': 'https://lvermgeo.rlp.de/produktinformationen/geotopografie/3d-geodaten/3d-gebaeudemodell',
        'download_url': 'https://geoshop.rlp.de/opendata-geb3dlo.html',
        'viewer_url': 'https://rlp.plexmap.de/v/RLP-in-3D-neu/',
        'license': 'DL-DE BY 2.0', 'license_url': BY,
        'format': 'CityGML', 'kind': 'download',
        'note': 'Amtliches LoD2 mit standardisierten Dachformen. Für eine '
                'native 3D-Karte muss CityGML vorab in 3D-Tiles oder '
                'geometrisch geeignete GeoJSON-Daten konvertiert werden. '
                'Der GeoShop meldet derzeit eingeschränkte Verfügbarkeit.'
    },
    'rp-dgm1': {
        'name': 'RP · Digitales Geländemodell DGM1 (1 m)',
        'topic': 'Gelände', 'region': 'Rheinland-Pfalz',
        'provider': 'LVermGeo Rheinland-Pfalz',
        'source_url': RLP_OPEN,
        'download_url': 'https://geoshop.rlp.de/opendata-dgm1.html',
        'license': 'DL-DE BY 2.0', 'license_url': BY,
        'format': 'ASCII XYZ / GeoTIFF', 'kind': 'download',
        'note': 'Original-DGM1 wird als amtlicher Download angeboten. Eine '
                'volle 1-km-Kachel kann die Grenzen des lokalen TAKT-Imports '
                'überschreiten; keine direkten Terrain-RGB-Tiles.'
    }
}

# DGM5/DGM10 are valid official downloads and are typically more manageable
# for local XYZ relief previews. They are NOT published as ready MapLibre tiles.
for resolution in (5, 10):
    DATASETS[f'rp-dgm{resolution}'] = {
        'name': f'RP · Digitales Geländemodell DGM{resolution} ({resolution} m)',
        'topic': 'Gelände', 'region': 'Rheinland-Pfalz',
        'provider': 'LVermGeo Rheinland-Pfalz',
        'source_url': RLP_OPEN,
        'download_url': 'https://geoshop.rlp.de/digitale_gelaendemodelle/digitale_gelaendemodelle_dgm.html',
        'license': 'DL-DE BY 2.0', 'license_url': BY,
        'format': 'ASCII XYZ / GeoTIFF', 'kind': 'download',
        'note': 'Amtlichen DGM-Datenausschnitt als ASCII-XYZ beziehen. '
                'Nach manuellem Import in Kartenlayer → DGM kann er mit '
                'einem LoD2-Modell vor Ort verglichen werden, wenn beide '
                'den Lage- und Höhenbezug EPSG:25832 / DHHN2016 besitzen. '
                'Keine automatisch streambare MapLibre-Datenquelle.'
    }


def discover(query='', region='', topic=''):
    """Cohesive read-only catalog used by the browser and tests.

    A catalog entry is a selectable service only if kind is a supported OGC
    type. Download datasets are clearly separate and never tile-proxied.
    """
    terms = query.casefold().split()
    def matches(item):
        return (not region or item['region'] == region) and (
            not topic or item['topic'] == topic) and all(
                word in ' '.join(str(v) for v in item.values()).casefold()
                for word in terms)
    return {
        'services': {k: dict(v) for k, v in CATALOG.items() if matches(v)},
        'datasets': {k: dict(v) for k, v in DATASETS.items() if matches(v)},
        'regions': sorted({v['region'] for v in (*CATALOG.values(), *DATASETS.values())}),
        'topics': sorted({v['topic'] for v in (*CATALOG.values(), *DATASETS.values())}),
    }


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
