from unittest.mock import MagicMock
from core.pages.alarms_page import AlarmsPage
from core.pages.incidents_page import IncidentsPage


def test_alarms_page_get_alarm_status_unfired():
    mock_page = MagicMock()
    mock_row = MagicMock()
    mock_row.is_visible.return_value = True

    mock_chk = MagicMock()
    mock_chk.is_visible.return_value = True
    mock_chk.is_checked.return_value = True

    mock_badge = MagicMock()
    mock_badge.is_visible.return_value = False

    mock_cell = MagicMock()
    mock_cell.locator.return_value.first = mock_badge

    mock_incident_icon = MagicMock()
    mock_incident_icon.is_visible.return_value = True

    def locator_side_effect(selector):
        loc = MagicMock()
        if "toggle_enabled" in selector:
            loc.first = mock_chk
            return loc
        if "td[data-label='Fired']" in selector:
            loc.first = mock_cell
            return loc
        if "td[data-label='Incident']" in selector:
            loc.first = mock_incident_icon
            return loc
        return loc

    mock_row.locator.side_effect = locator_side_effect
    mock_page.locator.return_value.filter.return_value.first = mock_row

    alarms_p = AlarmsPage(page=mock_page, base_url="https://10.1.33.160")
    status = alarms_p.get_alarm_status("test-alarm")

    assert status["present"] is True
    assert status["enabled"] is True
    assert status["fired"] is False
    assert status["incident_enabled"] is True


def test_alarms_page_get_alarm_status_fired():
    mock_page = MagicMock()
    mock_row = MagicMock()
    mock_row.is_visible.return_value = True

    mock_chk = MagicMock()
    mock_chk.is_visible.return_value = True
    mock_chk.is_checked.return_value = True

    mock_badge = MagicMock()
    mock_badge.is_visible.return_value = True
    mock_badge.inner_text.return_value = "Fired"

    mock_cell = MagicMock()
    mock_cell.locator.return_value.first = mock_badge

    mock_incident_icon = MagicMock()
    mock_incident_icon.is_visible.return_value = True

    def locator_side_effect(selector):
        loc = MagicMock()
        if "toggle_enabled" in selector:
            loc.first = mock_chk
            return loc
        if "td[data-label='Fired']" in selector:
            loc.first = mock_cell
            return loc
        if "td[data-label='Incident']" in selector:
            loc.first = mock_incident_icon
            return loc
        return loc

    mock_row.locator.side_effect = locator_side_effect
    mock_page.locator.return_value.filter.return_value.first = mock_row

    alarms_p = AlarmsPage(page=mock_page, base_url="https://10.1.33.160")
    status = alarms_p.get_alarm_status("test-alarm")

    assert status["present"] is True
    assert status["fired"] is True


def test_incidents_page_status():
    mock_page = MagicMock()
    mock_page.url = "https://10.1.33.160/incidents"
    mock_row = MagicMock()
    mock_row.is_visible.return_value = True

    mock_status_cell = MagicMock()
    mock_status_cell.is_visible.return_value = True

    mock_option = MagicMock()
    mock_option.inner_text.return_value = "New"

    mock_select = MagicMock()
    mock_select.count.return_value = 1
    mock_select.first = mock_option

    mock_status_cell.locator.return_value = mock_select
    mock_row.locator.return_value.first = mock_status_cell

    mock_page.locator.return_value.filter.return_value.first = mock_row

    incidents_p = IncidentsPage(page=mock_page, base_url="https://10.1.33.160")
    assert incidents_p.is_incident_present("test-alarm") is True
    assert incidents_p.get_incident_status("test-alarm") == "New"
