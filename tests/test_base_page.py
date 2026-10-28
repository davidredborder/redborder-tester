from unittest.mock import MagicMock
from core.pages.base_page import BasePage


def test_base_page_get_active_namespace():
    mock_page = MagicMock()
    mock_menu = MagicMock()
    mock_menu.is_visible.return_value = True
    mock_menu.inner_text.return_value = "rb-test-ns"
    mock_page.locator.return_value.first = mock_menu

    bp = BasePage(page=mock_page, base_url="https://10.1.33.160")
    assert bp.get_active_namespace() == "rb-test-ns"


def test_base_page_select_active_namespace_all():
    mock_page = MagicMock()
    mock_menu = MagicMock()
    mock_menu.is_visible.return_value = True

    # Dropdown toggle and menu
    mock_toggle = MagicMock()
    mock_dropdown = MagicMock()
    mock_dropdown.is_visible.return_value = True
    mock_all_checkbox = MagicMock()
    mock_all_checkbox.is_visible.return_value = True
    mock_all_checkbox.is_checked.return_value = False
    mock_apply_btn = MagicMock()
    mock_apply_btn.is_visible.return_value = True

    def locator_side_effect(selector):
        loc = MagicMock()
        if "namespace-menu" in selector:
            loc.first = mock_menu
            return loc
        if "dropdown-toggle" in selector:
            loc.first = mock_toggle
            return loc
        if "dropdown-menu" in selector:
            loc.first = mock_dropdown
            return loc
        if "#namespace_all" in selector:
            loc.first = mock_all_checkbox
            return loc
        if "apply-namespaces" in selector:
            loc.first = mock_apply_btn
            return loc
        return loc

    mock_menu.locator.side_effect = locator_side_effect
    mock_page.locator.side_effect = locator_side_effect

    bp = BasePage(page=mock_page, base_url="https://10.1.33.160")
    result = bp.select_active_namespace("All")

    assert result is True
    mock_all_checkbox.click.assert_called_once()
    mock_apply_btn.click.assert_called_once()


def test_base_page_select_active_namespace_specific():
    mock_page = MagicMock()
    mock_menu = MagicMock()
    mock_menu.is_visible.return_value = True

    mock_toggle = MagicMock()
    mock_dropdown = MagicMock()
    mock_dropdown.is_visible.return_value = True

    mock_target_chk = MagicMock()
    mock_target_chk.is_visible.return_value = True
    mock_target_chk.is_checked.return_value = False

    mock_apply_btn = MagicMock()
    mock_apply_btn.is_visible.return_value = True

    def locator_side_effect(selector):
        loc = MagicMock()
        if "namespace-menu" in selector:
            loc.first = mock_menu
            return loc
        if "dropdown-toggle" in selector:
            loc.first = mock_toggle
            return loc
        if "dropdown-menu" in selector:
            loc.first = mock_dropdown
            return loc
        if "rb-test-ns" in selector:
            loc.first = mock_target_chk
            return loc
        if "apply-namespaces" in selector:
            loc.first = mock_apply_btn
            return loc
        return loc

    mock_menu.locator.side_effect = locator_side_effect
    mock_page.locator.side_effect = locator_side_effect

    bp = BasePage(page=mock_page, base_url="https://10.1.33.160")
    result = bp.select_active_namespace("rb-test-ns")

    assert result is True
    mock_target_chk.click.assert_called_once()
    mock_apply_btn.click.assert_called_once()
