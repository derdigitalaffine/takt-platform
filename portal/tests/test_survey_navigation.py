"""My Surveys is a contextual part of Surveys & Votes, not a main-menu item."""
from conftest import login, settings
from test_my_surveys import workspace


def test_member_sees_only_survey_module_in_main_menu_and_personal_page(workspace):
    user = login("my-surveys-member@example.org", "personal-survey-test-123")
    homepage = user.get("/")
    assert homepage.status_code == 200
    assert 'data-nav-id="my_surveys"' not in homepage.text
    assert 'data-nav-id="surveys"' in homepage.text
    selection = user.get("/umfragen", follow_redirects=False)
    assert selection.status_code == 303
    assert selection.headers["location"] == "/meine-umfragen"
    page = user.get("/meine-umfragen")
    assert page.status_code == 200
    assert 'href="/meine-umfragen" aria-current="page"' in page.text
    assert "Meine Feedbackrunde" in page.text
    assert "Meine vertrauliche Abstimmung" in page.text
    assert "Umfragen verwalten</a>" not in page.text


def test_manager_sees_both_module_sections_without_another_sidebar_link(workspace):
    admin = login("admin@example.org", "admin-passwort-123")
    homepage = admin.get("/")
    assert 'data-nav-id="my_surveys"' not in homepage.text
    assert 'data-nav-id="surveys"' in homepage.text
    manager = admin.get("/umfragen")
    assert manager.status_code == 200
    assert 'href="/meine-umfragen"' in manager.text
    assert 'href="/umfragen" aria-current="page"' in manager.text
    personal = admin.get("/meine-umfragen")
    assert personal.status_code == 200
    assert 'href="/umfragen"' in personal.text
    assert 'href="/meine-umfragen" aria-current="page"' in personal.text


def test_form_only_personal_workspace_remains_available_without_poll_module(workspace):
    settings(module_forms="1", module_polls="0")
    c = login("my-surveys-member@example.org", "personal-survey-test-123")
    personal = c.get("/meine-umfragen")
    assert personal.status_code == 200
    assert "Meine Feedbackrunde" in personal.text
    assert "Meine vertrauliche Abstimmung" not in personal.text
    assert 'data-nav-id="my_surveys"' not in c.get("/").text
    assert c.get("/umfragen").status_code == 404
