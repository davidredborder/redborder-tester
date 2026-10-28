import time
import pytest
from playwright.sync_api import expect
from core.pages.alarms_page import AlarmsPage
from core.pages.incidents_page import IncidentsPage
from core.ssh_client import SSHClient


@pytest.mark.web
@pytest.mark.alarms
class TestAlarmsLifecycle:
    """End-to-end tests for the Redborder Alarms & Incidents module:
    1. Alarm creation with threshold and incident generation enabled.
    2. Alarm evaluation and firing triggered by stopping telemetry on a sensor.
    3. Incident creation verification on /incidents.
    4. Alarm rearming / reactivation via Web UI after telemetry restoration.
    5. Resilient teardown of test alarm and incident.
    """

    def test_alarm_sensor_packet_loss_firing_incident_and_rearm(
        self,
        alarms_page: AlarmsPage,
        incidents_page: IncidentsPage,
        ssh_client: SSHClient,
        require_redborder_sensors,
        attach_screenshot,
    ):
        alarm_name = f"rb-alarm-snmp-loss-{int(time.time())}"
        target_sensor_name = "rb-snmp-test"
        mock_sensor_name = "rb-snmp"

        # --- Phase 1: Pre-condition check ---
        print("[E2E Alarms] Checking alarm engine service status...")
        assert ssh_client.is_service_active("redborder-alarm-engine.service"), (
            "redborder-alarm-engine.service is not active"
        )

        print(f"[E2E Alarms] Ensuring mock sensor '{mock_sensor_name}' is running...")
        if not ssh_client.is_mock_sensor_running(mock_sensor_name):
            ssh_client.start_mock_sensor(name=mock_sensor_name, ip="10.10.10.4", agent_type="snmp")
            time.sleep(5)
        assert ssh_client.is_mock_sensor_running(mock_sensor_name), (
            f"Failed to start mock sensor '{mock_sensor_name}'"
        )

        # Select all namespaces in top bar so everything is visible
        alarms_page.select_active_namespace("All")

        created = False
        incident_created = False
        try:
            # --- Phase 2: Create Test Alarm via Web UI ---
            print(f"[E2E Alarms] Creating monitor ping loss alarm '{alarm_name}' on sensor '{target_sensor_name}'...")
            created = alarms_page.create_alarm(
                name=alarm_name,
                product_type="monitor",
                monitor_tab="pkts_lost",
                sensor_name=target_sensor_name,
                upper_limit=10,
                treat_missing_as_zero=True,
                incident_enabled=True,
                auto_reactivate=False,
            )
            assert created, f"Failed to create alarm '{alarm_name}' via Web UI"
            print(f"[E2E Alarms] Alarm '{alarm_name}' successfully created.")

            # Verify initial state: present and NOT fired
            status = alarms_page.get_alarm_status(alarm_name)
            assert status["present"], f"Alarm '{alarm_name}' not found in alarms table"
            assert status["enabled"], f"Alarm '{alarm_name}' should be enabled"
            assert not status["fired"], f"Alarm '{alarm_name}' should not be fired initially"
            assert status["incident_enabled"], f"Alarm '{alarm_name}' should have incident generation enabled"
            attach_screenshot(alarms_page.page, title="Alarms - Initial Created State (Unfired)")

            # --- Phase 3: Stop Telemetry to Trigger Alarm Firing ---
            print(f"[E2E Alarms] Stopping mock sensor '{mock_sensor_name}' to trigger packet loss trip...")
            ssh_client.stop_mock_sensor(mock_sensor_name)
            assert not ssh_client.is_mock_sensor_running(mock_sensor_name), (
                f"Mock sensor '{mock_sensor_name}' is still running"
            )

            # --- Phase 4: Wait for Alarm Engine to Fire the Alarm ---
            print(f"[E2E Alarms] Waiting for alarm engine to evaluate and fire '{alarm_name}'...")
            fired = False
            # Alarm engine runs every 30s. Monitor updates every 60s. Poll for up to 120 seconds.
            for attempt in range(24):
                time.sleep(5)
                alarms_page.open_alarms()
                alarms_page.select_active_namespace("All")
                if alarms_page.is_alarm_fired(alarm_name):
                    fired = True
                    print(f"[E2E Alarms] Alarm '{alarm_name}' fired on attempt {attempt + 1}!")
                    break

            attach_screenshot(alarms_page.page, title="Alarms - Alarm Fired State")
            assert fired, (
                f"Alarm '{alarm_name}' did not transition to FIRED status within 120s after stopping telemetry"
            )

            # Verify reactivate button is visible
            alarm_row = alarms_page.get_alarm_row(alarm_name)
            reactivate_btn = alarm_row.locator("a.reactivate_alarm_button").first
            expect(reactivate_btn).to_be_visible(timeout=5000)
            print(f"[E2E Alarms] Reactivate/rearm button verified visible on alarm row.")

            # --- Phase 5: Verify Incident Creation on /incidents ---
            print("[E2E Alarms] Processing pending incident visibility via background job...")
            ssh_client.sync_pending_incidents()

            print("[E2E Alarms] Navigating to /incidents to verify incident generation...")
            incidents_page.open_incidents()
            incidents_page.select_active_namespace("All")

            # Check that incident is present
            incident_present = False
            for attempt in range(8):
                if incidents_page.is_incident_present(alarm_name):
                    incident_present = True
                    incident_created = True
                    break
                time.sleep(3)
                ssh_client.sync_pending_incidents()
                incidents_page.open_incidents()

            attach_screenshot(incidents_page.page, title="Incidents - Incident Created by Alarm")
            assert incident_present, (
                f"Incident for alarm '{alarm_name}' was not found on /incidents table"
            )

            incident_status = incidents_page.get_incident_status(alarm_name)
            print(f"[E2E Alarms] Incident status for '{alarm_name}': {incident_status}")
            assert incident_status is not None, "Could not determine incident status"
            assert incident_status.lower() == "new", f"Expected incident status 'New', got '{incident_status}'"

            # --- Phase 6: Telemetry Restoration & Rearming ---
            print(f"[E2E Alarms] Restarting mock sensor '{mock_sensor_name}'...")
            ssh_client.start_mock_sensor(name=mock_sensor_name, ip="10.10.10.4", agent_type="snmp")
            time.sleep(5)
            assert ssh_client.is_mock_sensor_running(mock_sensor_name), (
                f"Failed to restart mock sensor '{mock_sensor_name}'"
            )

            print(f"[E2E Alarms] Navigating back to /alarms to reactivate/rearm '{alarm_name}'...")
            alarms_page.open_alarms()
            alarms_page.select_active_namespace("All")

            rearmed = alarms_page.reactivate_alarm(alarm_name, timeout_seconds=15)
            attach_screenshot(alarms_page.page, title="Alarms - Alarm Rearmed / Reactivated")
            assert rearmed, f"Alarm '{alarm_name}' failed to rearm/reactivate via Web UI"
            print(f"[E2E Alarms] Alarm '{alarm_name}' successfully rearmed. Fired status cleared.")

        finally:
            # Always ensure mock sensor is restored
            try:
                if not ssh_client.is_mock_sensor_running(mock_sensor_name):
                    ssh_client.start_mock_sensor(name=mock_sensor_name, ip="10.10.10.4", agent_type="snmp")
            except Exception as e:
                print(f"[E2E Alarms Teardown Warning] Failed to ensure mock sensor '{mock_sensor_name}' running: {e}")

            # --- Phase 7: Resilient Teardown ---
            print(f"[E2E Alarms Teardown] Cleaning up test alarm '{alarm_name}'...")
            if created:
                try:
                    alarms_page.open_alarms()
                    alarms_page.delete_alarm(alarm_name)
                    print(f"[E2E Alarms Teardown] Test alarm '{alarm_name}' deleted.")
                except Exception as e:
                    print(f"[E2E Alarms Teardown Warning] Failed to delete alarm '{alarm_name}': {e}")

                # Also ensure associated incident is deleted if created
                try:
                    incidents_page.open_incidents()
                    incidents_page.delete_incident(alarm_name)
                    print(f"[E2E Alarms Teardown] Test incident for '{alarm_name}' deleted.")
                except Exception as e:
                    print(f"[E2E Alarms Teardown Warning] Failed to delete incident for '{alarm_name}': {e}")
