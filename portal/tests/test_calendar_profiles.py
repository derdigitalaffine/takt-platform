import plistlib
import pytest
from app.calendar_profiles import ios_profile


def test_device_password_and_names_are_safely_encoded_in_apple_profile():
    secret = 'device-only<&"secret'
    profile = ios_profile(
        server_url="https://takt.example.org/portal",
        device_username="device:a/b",
        device_password=secret,
        account_name="Takt <Kalender>",
    )
    decoded = plistlib.loads(profile)
    account = decoded["PayloadContent"][0]
    assert account["CalDAVPassword"] == secret
    assert (
        account["CalDAVPrincipalURL"]
        == "https://takt.example.org/portal/caldav/principals/device%3Aa%2Fb/"
    )
    assert account["CalDAVUseSSL"] is True and account["CalDAVPort"] == 443
    assert account["PayloadType"] == "com.apple.caldav.account"
    assert b"<Kalender>" not in profile


@pytest.mark.parametrize(
    "url",
    [
        "http://takt.example.org",
        "https://u:p@takt.example.org",
        "https://takt.example.org/?secret=x",
        "https://takt.example.org/#secret",
        "https://takt.example.org:99999",
    ],
)
def test_insecure_or_credential_bearing_server_urls_are_rejected(url):
    with pytest.raises(ValueError):
        ios_profile(
            server_url=url,
            device_username="device",
            device_password="only-device-secret",
        )
