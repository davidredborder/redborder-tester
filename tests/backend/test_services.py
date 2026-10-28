import pytest
from core.ssh_client import SSHClient

CORE_SERVICES = [
    "chef-client.service",
    "chronyd.service",
    "consul.service",
    "druid-broker",
    "druid-coordinator",
    "druid-historical",
    "druid-indexer",
    "druid-overlord",
    "druid-router",
    "f2k.service",
    "firewalld.service",
    "http2k.service",
    "kafka.service",
    "logstash.service",
    "memcached.service",
    "minio.service",
    "nginx.service",
    "opscode-erchef.service",
    "postgresql.service",
    "rb-druid-indexer.service",
    "rb-workers.service",
    "redborder-alarm-engine.service",
    "redborder-hub.service",
    "redborder-license.service",
    "redborder-mem2incident.service",
    "redborder-monitor.service",
    "redis.service",
    "rsyslog.service",
    "sfacctd.service",
    "snmptrapd.service",
    "webui.service",
    "zookeeper.service",
]


@pytest.mark.backend
@pytest.mark.smoke
class TestBackendServices:
    @pytest.mark.parametrize("service_name", CORE_SERVICES)
    def test_core_service_is_active(self, ssh_client: SSHClient, service_name: str):
        """Verifies that each core systemd service is loaded and actively running."""
        is_active = ssh_client.is_service_active(service_name)
        status_info = ""
        if not is_active:
            if service_name == "sfacctd.service" and ssh_client.is_service_active("x2kafka.service"):
                pytest.skip("sfacctd.service is superseded by active x2kafka.service on this appliance")
            res = ssh_client.get_service_status(service_name)
            status_info = f"\n--- Service Status ---\n{res.stdout}\n{res.stderr}"

        assert is_active, f"Service '{service_name}' is not active!{status_info}"

    def test_listening_ports(self, ssh_client: SSHClient):
        """Verifies that HTTP (80) and HTTPS (443) ports are listening."""
        result = ssh_client.run("ss -tulpn | grep -E ':(80|443) '")
        assert result.ok, f"Failed to query network sockets: {result.stderr}"
        assert ":80" in result.stdout, "Port 80 is not listening"
        assert ":443" in result.stdout, "Port 443 is not listening"

    def test_disk_space_healthy(self, ssh_client: SSHClient):
        """Verifies that disk usage on root filesystem is below 90%."""
        result = ssh_client.run("df -h / | awk 'NR==2 {print $5}'")
        assert result.ok, f"Failed to check disk usage: {result.stderr}"
        percent_str = result.stdout.strip().replace("%", "")
        usage_pct = int(percent_str)
        assert usage_pct < 90, f"Root filesystem usage is critically high: {usage_pct}%"

    def test_webui_service_journal_no_fatal_crashes(self, ssh_client: SSHClient):
        """Checks recent webui service journal logs for fatal crashes."""
        result = ssh_client.run("journalctl -u webui.service -n 50 --no-pager")
        assert result.ok, f"Failed to read webui journal logs: {result.stderr}"
        assert "SIGSEGV" not in result.stdout, "Found segmentation fault in webui logs!"
        assert "FATAL" not in result.stdout, "Found FATAL crash in webui logs!"
