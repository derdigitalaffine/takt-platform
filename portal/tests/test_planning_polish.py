"""Compile all calendar and leave UI templates against the real Takt Jinja setup.

This also guards the rarely visited one-time token screens, public calendars,
device help and audit pages against malformed block endings.
"""

from app.main import templates


def test_planning_polish_templates_compile():
    names = (
        "calendars.html",
        "calendar_sharing.html",
        "calendar_devices.html",
        "calendar_device_created.html",
        "calendar_feeds.html",
        "calendar_feed_created.html",
        "calendar_help.html",
        "calendar_public.html",
        "leave.html",
        "leave_config.html",
        "leave_management.html",
        "leave_history.html",
    )
    for name in names:
        assert templates.env.get_template(name) is not None, name
