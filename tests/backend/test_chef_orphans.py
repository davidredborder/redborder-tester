"""Chef Orphan Audit Test Suite.

Audits the Chef Infra Server node registry against active Rails database sensors.
Detects any orphaned Chef nodes left behind when sensors were deleted in the Web UI,
preventing stale configuration, IP mapping collisions, and rsyslog tag corruptions.
"""

import pytest
from core.ssh_client import SSHClient


@pytest.mark.backend
def test_no_orphaned_chef_nodes(ssh_client: SSHClient):
    """Audits Chef Infra Server node registry against active Rails database sensors.

    Fails with detailed diagnostic metadata if any sensor Chef node exists on Chef Server
    without a corresponding active Sensor record in Rails database.
    """
    orphans = ssh_client.find_orphaned_chef_nodes()

    if orphans:
        orphan_details = "\n".join(
            f" - Chef Node: {o['node_name']} (Sensor ID: {o.get('sensor_id')}, "
            f"Type: {o.get('type')}, IP: {o.get('ip')}, RB Name: {o.get('rbname')})"
            for o in orphans
        )
        error_msg = (
            f"Platform Defect Detected: Found {len(orphans)} orphaned Chef node(s) on Chef Server!\n"
            f"When sensors are deleted, the platform must cleanly purge their node from Chef Infra Server.\n"
            f"Orphaned nodes:\n{orphan_details}"
        )
        pytest.fail(error_msg)
