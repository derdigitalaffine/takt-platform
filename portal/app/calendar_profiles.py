"""Apple CalDAV profile generation for a newly issued personal device credential.

Return bytes directly to the authenticated setup response; never persist this
profile, log it, or use the portal account password as device_password.
"""

import plistlib
import uuid
from urllib.parse import quote, urlsplit


def ios_profile(
    *,
    server_url: str,
    device_username: str,
    device_password: str,
    account_name: str = "Takt Kalender"
) -> bytes:
    url = urlsplit(server_url)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "Für Kalenderprofile ist eine gültige HTTPS-Serveradresse erforderlich."
        )
    try:
        port = url.port or 443
    except ValueError as exc:
        raise ValueError("Ungültiger Serverport.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Ungültiger Serverport.")
    if (
        not device_username
        or len(device_username) > 200
        or not device_password
        or len(device_password) > 512
    ):
        raise ValueError("Ein neu erzeugter Gerätezugang ist erforderlich.")
    if any(ord(c) < 32 for c in device_username + device_password + account_name):
        raise ValueError("Steuerzeichen sind nicht erlaubt.")
    base = server_url.rstrip("/")
    identifier = "org.takt.calendar." + uuid.uuid4().hex
    account = {
        "PayloadType": "com.apple.caldav.account",
        "PayloadVersion": 1,
        "PayloadIdentifier": identifier + ".account",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadDisplayName": account_name[:200],
        "CalDAVAccountDescription": account_name[:200],
        "CalDAVHostName": url.hostname,
        "CalDAVPort": port,
        "CalDAVUseSSL": True,
        "CalDAVPrincipalURL": base
        + "/caldav/principals/"
        + quote(device_username, safe="")
        + "/",
        "CalDAVUsername": device_username,
        "CalDAVPassword": device_password,
    }
    return plistlib.dumps(
        {
            "PayloadType": "Configuration",
            "PayloadVersion": 1,
            "PayloadIdentifier": identifier,
            "PayloadUUID": str(uuid.uuid4()).upper(),
            "PayloadDisplayName": account_name[:200],
            "PayloadDescription": "Persönlicher Kalenderzugang für dieses Gerät. In Takt einzeln widerrufbar.",
            "PayloadContent": [account],
        },
        fmt=plistlib.FMT_XML,
        sort_keys=False,
    )
