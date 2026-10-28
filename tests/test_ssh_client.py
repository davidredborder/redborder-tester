import json
from unittest.mock import MagicMock, patch
from core.ssh_client import SSHClient, CommandResult


def test_command_result_dataclass():
    res = CommandResult(exit_code=0, stdout="hello", stderr="")
    assert res.ok is True
    assert res.stdout == "hello"

    res_fail = CommandResult(exit_code=1, stdout="", stderr="error")
    assert res_fail.ok is False


@patch("paramiko.SSHClient")
def test_ssh_client_run(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"active\n"

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        result = client.run("systemctl is-active webui.service")
        assert result.ok is True
        assert "active" in result.stdout


@patch("paramiko.SSHClient")
def test_ssh_client_mock_sensor_and_druid(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b'[{"total": 880}]'

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        count = client.query_druid_flow_count(sensor_name="flow1", sensor_ip="10.10.10.2")
        assert count == 880

        # Check command sent contains where clause
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "sensor_name" in called_cmd
        assert "flow1" in called_cmd
        assert "sensor_ip" in called_cmd
        assert "10.10.10.2" in called_cmd


@patch("paramiko.SSHClient")
def test_ssh_client_query_druid_sensor_flows(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b'[{"sensor_name": "flow1", "sensor_ip": "10.10.10.2", "sum_pkts": 25}]'

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        rows = client.query_druid_sensor_flows(sensor_name="flow1", limit=1)
        assert len(rows) == 1
        assert rows[0]["sensor_name"] == "flow1"
        assert rows[0]["sum_pkts"] == 25


@patch("paramiko.SSHClient")
def test_ssh_client_query_druid_vault(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b'[{"total": 42}]'

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        count = client.query_druid_vault_count(sensor_name="vault1", sensor_ip="10.10.10.3")
        assert count == 42
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "rb_vault" in called_cmd
        assert "vault1" in called_cmd


@patch("paramiko.SSHClient")
def test_ssh_client_snmpwalk(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"SNMPv2-MIB::sysDescr.0 = STRING: Cisco Switch\n"

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        res = client.snmpwalk_query("10.10.10.4", community="redBorder")
        assert res.ok is True
        assert "Cisco Switch" in res.stdout
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "snmpwalk" in called_cmd
        assert "redBorder" in called_cmd
        assert "10.10.10.4" in called_cmd


@patch("paramiko.SSHClient")
def test_ssh_client_webserver_and_http_agent(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b'{"status": 200, "message": "OK"}\n'

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        # 1. start webserver
        res_start = client.start_mock_webserver(name="web1", ip="10.10.10.50", config_name="config-headers.json")
        assert res_start.ok is True
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "sensor-ctl.sh start web1 --ip 10.10.10.50 webserver" in called_cmd
        assert "config-headers.json" in called_cmd

        # 2. run http agent check
        res_check = client.run_http_agent_check(
            url="http://10.10.10.50/auth",
            method="GET",
            expected_status=200,
            auth_type="basic",
            username="admin",
            password="secret",
            headers={"X-Test": "1"},
        )
        assert res_check.ok is True
        called_check = mock_instance.exec_command.call_args[0][0]
        assert "rb_http_agent.rb" in called_check
        assert "-u http://10.10.10.50/auth" in called_check
        assert "-a basic -U admin -P secret" in called_check
        assert "X-Test" in called_check

        # 3. stop webserver
        res_stop = client.stop_mock_webserver(name="web1")
        assert res_stop.ok is True
        called_stop = mock_instance.exec_command.call_args[0][0]
        assert "sensor-ctl.sh stop web1" in called_stop


@patch("paramiko.SSHClient")
def test_ssh_client_is_redborder_sensors_installed(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"redborder-sensors-1.0.0-1.el9.x86_64\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        assert client.is_redborder_sensors_installed() is True
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "rpm -q redborder-sensors" in called_cmd or "sensor-ctl" in called_cmd


@patch("paramiko.SSHClient")
def test_ssh_client_ensure_redborder_sensors_installed(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    # 1. Already installed scenario
    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"installed\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        assert client.ensure_redborder_sensors_installed() is True

    # 2. Missing, installation succeeds scenario
    mock_stdout_missing = MagicMock()
    mock_stdout_missing.channel.recv_exit_status.return_value = 1
    mock_stdout_missing.read.return_value = b"not installed\n"

    mock_stdout_install = MagicMock()
    mock_stdout_install.channel.recv_exit_status.return_value = 0
    mock_stdout_install.read.return_value = b"Complete!\n"

    mock_stdout_check_after = MagicMock()
    mock_stdout_check_after.channel.recv_exit_status.return_value = 0
    mock_stdout_check_after.read.return_value = b"installed\n"

    mock_instance.exec_command.side_effect = [
        (MagicMock(), mock_stdout_missing, mock_stderr),
        (MagicMock(), mock_stdout_install, mock_stderr),
        (MagicMock(), mock_stdout_check_after, mock_stderr),
    ]

    with client:
        assert client.ensure_redborder_sensors_installed() is True

    # 3. Missing, installation fails scenario
    mock_stdout_fail_install = MagicMock()
    mock_stdout_fail_install.channel.recv_exit_status.return_value = 1
    mock_stdout_fail_install.read.return_value = b"No match for argument: redborder-sensors\n"

    mock_instance.exec_command.side_effect = [
        (MagicMock(), mock_stdout_missing, mock_stderr),
        (MagicMock(), mock_stdout_fail_install, mock_stderr),
        (MagicMock(), mock_stdout_missing, mock_stderr),
    ]

    with client:
        assert client.ensure_redborder_sensors_installed() is False


@patch("paramiko.SSHClient")
def test_ssh_client_is_druid_ready(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"HTTP/1.1 200 OK\n\ntrue\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        assert client.is_druid_ready() is True
        cmd = mock_instance.exec_command.call_args[0][0]
        assert "/status/health" in cmd


@patch("paramiko.SSHClient")
def test_ssh_client_wait_for_druid_ready(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    # 1. Immediate ready
    mock_stdout_ready = MagicMock()
    mock_stdout_ready.channel.recv_exit_status.return_value = 0
    mock_stdout_ready.read.return_value = b"true\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout_ready, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        assert client.wait_for_druid_ready(timeout=5, interval=1) is True

    # 2. Down then ready
    mock_stdout_down = MagicMock()
    mock_stdout_down.channel.recv_exit_status.return_value = 1
    mock_stdout_down.read.return_value = b"Failed to connect\n"

    mock_instance.exec_command.side_effect = [
        (MagicMock(), mock_stdout_down, mock_stderr),
        (MagicMock(), mock_stdout_ready, mock_stderr),
    ]
    with client:
        assert client.wait_for_druid_ready(timeout=5, interval=0.1) is True


@patch("paramiko.SSHClient")
def test_ssh_client_converge_chef_and_wait_druid(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout_chef = MagicMock()
    mock_stdout_chef.channel.recv_exit_status.return_value = 0
    mock_stdout_chef.read.return_value = b"Chef run complete\n"

    mock_stdout_druid = MagicMock()
    mock_stdout_druid.channel.recv_exit_status.return_value = 0
    mock_stdout_druid.read.return_value = b"true\n"

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    # Alternates between chef-client and druid check
    mock_instance.exec_command.side_effect = [
        (MagicMock(), mock_stdout_chef, mock_stderr),
        (MagicMock(), mock_stdout_druid, mock_stderr),
    ]

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        res = client.converge_chef_and_wait_druid(iterations=1, druid_timeout=5, chef_timeout=10)
        assert res is True


@patch("paramiko.SSHClient")
def test_ssh_client_rebuild_sensor_tree(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"Tree bounds rebuilt successfully\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        res = client.rebuild_sensor_tree()
        assert res.ok is True
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "Sensor.rebuild!(false)" in called_cmd


@patch("paramiko.SSHClient")
def test_ssh_client_get_chef_node_list(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"cep\nrbflow-2\nrbvault-193\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        nodes = client.get_chef_node_list()
        assert nodes == ["cep", "rbflow-2", "rbvault-193"]


@patch("paramiko.SSHClient")
def test_ssh_client_get_rails_sensor_ids(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"[1, 2, 4, 5, 94, 95]\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        ids = client.get_rails_sensor_ids()
        assert ids == {1, 2, 4, 5, 94, 95}


@patch("paramiko.SSHClient")
def test_ssh_client_find_orphaned_chef_nodes(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    # 1. get_chef_node_list returns nodes
    mock_stdout_nodes = MagicMock()
    mock_stdout_nodes.channel.recv_exit_status.return_value = 0
    mock_stdout_nodes.read.return_value = b"cep\nrbflow-2\nrbvault-193\n"

    # 2. get_rails_sensor_ids returns [2] (193 is missing from Rails)
    mock_stdout_ids = MagicMock()
    mock_stdout_ids.channel.recv_exit_status.return_value = 0
    mock_stdout_ids.read.return_value = b"[2]\n"

    # 3. knife node show rbvault-193 -F json
    node_193_json = json.dumps({
        "name": "rbvault-193",
        "default": {
            "redborder": {
                "sensor": {
                    "ip": "10.10.10.3",
                    "rbname": "rb-vault-old",
                    "sensor_type": "vault"
                }
            }
        }
    }).encode("utf-8")
    mock_stdout_node = MagicMock()
    mock_stdout_node.channel.recv_exit_status.return_value = 0
    mock_stdout_node.read.return_value = node_193_json

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.side_effect = [
        (MagicMock(), mock_stdout_nodes, mock_stderr),
        (MagicMock(), mock_stdout_ids, mock_stderr),
        (MagicMock(), mock_stdout_node, mock_stderr),
    ]

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        orphans = client.find_orphaned_chef_nodes()
        assert len(orphans) == 1
        assert orphans[0]["node_name"] == "rbvault-193"
        assert orphans[0]["sensor_id"] == 193
        assert orphans[0]["ip"] == "10.10.10.3"
        assert orphans[0]["rbname"] == "rb-vault-old"


@patch("paramiko.SSHClient")
def test_ssh_client_all_baseline_mock_sandboxes(mock_ssh):
    mock_instance = MagicMock()
    mock_ssh.return_value = mock_instance

    mock_stdout_list = MagicMock()
    mock_stdout_list.channel.recv_exit_status.return_value = 0
    mock_stdout_list.read.return_value = b"name ip agent state\n"

    mock_stdout_cmd = MagicMock()
    mock_stdout_cmd.channel.recv_exit_status.return_value = 0
    mock_stdout_cmd.read.return_value = b"OK\n"

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout_cmd, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        client.start_all_baseline_mock_sandboxes()
        client.stop_all_baseline_mock_sandboxes()


@patch("paramiko.SSHClient")
def test_ssh_client_get_druid_tables(mock_ssh):
    mock_instance = MagicMock()
    mock_ssh.return_value = mock_instance

    mock_stdout_cmd = MagicMock()
    mock_stdout_cmd.channel.recv_exit_status.return_value = 0
    # JSON output from druid query returning TABLE_NAME rows
    mock_stdout_cmd.read.return_value = b'[{"TABLE_NAME": "rb_vault"}, {"TABLE_NAME": "rb_vault_abc123"}]\n'

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout_cmd, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        tables = client.get_druid_tables("rb_vault")
        assert "rb_vault" in tables
        assert "rb_vault_abc123" in tables
        # Also verify backward-compatible private method
        assert client._get_druid_tables("rb_vault") == tables


@patch("paramiko.SSHClient")
def test_ssh_client_sync_pending_incidents(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout_cmd = MagicMock()
    mock_stdout_cmd.channel.recv_exit_status.return_value = 0
    mock_stdout_cmd.read.return_value = b"Searching for non visible incidents...\n1 incidents found (processing all).\n"

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout_cmd, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        res = client.sync_pending_incidents()
        assert res.ok is True
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "rvm use ruby-3.4.11@web" in called_cmd
        assert "RAILS_ENV=production bundle exec bin/rails runner" in called_cmd
        assert "Redborder::Jobs::UpdateContentIncidentsJob.new(false, 1).perform" in called_cmd


@patch("paramiko.SSHClient")
def test_ssh_client_rebuild_sensor_tree(mock_paramiko_cls):
    mock_instance = MagicMock()
    mock_paramiko_cls.return_value = mock_instance

    mock_stdout_cmd = MagicMock()
    mock_stdout_cmd.channel.recv_exit_status.return_value = 0
    mock_stdout_cmd.read.return_value = b"true\n"

    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    mock_instance.exec_command.return_value = (MagicMock(), mock_stdout_cmd, mock_stderr)

    client = SSHClient(host="10.1.33.160", username="root", password="dummy")
    with client:
        res = client.rebuild_sensor_tree()
        assert res.ok is True
        called_cmd = mock_instance.exec_command.call_args[0][0]
        assert "rvm use ruby-3.4.11@web" in called_cmd
        assert "Sensor.rebuild!(false)" in called_cmd

