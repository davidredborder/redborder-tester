"""Page Object Model (POM) classes for Redborder Web UI."""
from core.pages.base_page import BasePage
from core.pages.login_page import LoginPage
from core.pages.dashboard_page import DashboardPage
from core.pages.sensors_page import SensorsPage
from core.pages.traffic_page import TrafficPage
from core.pages.vault_page import VaultPage
from core.pages.monitor_page import MonitorPage
from core.pages.users_page import UsersPage
from core.pages.alarms_page import AlarmsPage
from core.pages.incidents_page import IncidentsPage

__all__ = [
    "BasePage",
    "LoginPage",
    "DashboardPage",
    "SensorsPage",
    "TrafficPage",
    "VaultPage",
    "MonitorPage",
    "UsersPage",
    "AlarmsPage",
    "IncidentsPage",
]
