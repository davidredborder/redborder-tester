import json
import re
import shlex
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
import paramiko


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SSHClient:
    def __init__(
        self,
        host: str,
        username: str = "root",
        password: Optional[str] = None,
        port: int = 22,
        timeout: int = 10,
        key_filename: Optional[str] = None,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.key_filename = key_filename
        self._client: Optional[paramiko.SSHClient] = None

    def connect(self) -> "SSHClient":
        if self._client is not None:
            return self

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            key_filename=self.key_filename,
            timeout=self.timeout,
            look_for_keys=False if self.password else True,
            allow_agent=False if self.password else True,
        )
        self._client = client
        return self

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> "SSHClient":
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def run(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        if self._client is None:
            self.connect()

        if self._client is None:
            raise RuntimeError("SSH client is not connected")

        effective_timeout = self.timeout if timeout is None else timeout
        stdin, stdout, stderr = self._client.exec_command(
            command, timeout=effective_timeout
        )
        # Read buffers before channel recv_exit_status to prevent Paramiko channel window deadlock
        out_bytes = stdout.read()
        err_bytes = stderr.read()
        exit_code = stdout.channel.recv_exit_status()

        out_str = out_bytes.decode("utf-8", errors="replace")
        err_str = err_bytes.decode("utf-8", errors="replace")
        return CommandResult(exit_code=exit_code, stdout=out_str, stderr=err_str)

    def is_service_active(self, service_name: str) -> bool:
        cmd = f"systemctl is-active {shlex.quote(service_name)}"
        res = self.run(cmd)
        return res.stdout.strip() == "active"

    def get_service_status(self, service_name: str) -> CommandResult:
        cmd = f"systemctl status {shlex.quote(service_name)} --no-pager"
        return self.run(cmd)

    # --- redborder-sensors Helpers ---
    def is_redborder_sensors_installed(self) -> bool:
        """Checks if the redborder-sensors package is installed and operational on the appliance."""
        cmd = "rpm -q redborder-sensors || test -x /usr/libexec/redborder-sensors/sensor-ctl.sh"
        res = self.run(cmd, timeout=15)
        return res.ok

    def install_redborder_sensors(self) -> CommandResult:
        """Attempts to install redborder-sensors via dnf on the appliance."""
        cmd = "dnf install -y redborder-sensors"
        return self.run(cmd, timeout=180)

    def ensure_redborder_sensors_installed(self) -> bool:
        """Verifies redborder-sensors is installed. If missing, attempts 'dnf install -y redborder-sensors'.

        Returns True if installed or successfully installed, False otherwise.
        """
        if self.is_redborder_sensors_installed():
            return True

        res = self.install_redborder_sensors()
        if res.ok or self.is_redborder_sensors_installed():
            return True

        return False

    def start_mock_sensor(
        self,
        name: str = "flow1",
        ip: str = "10.10.10.2",
        target_ip: Optional[str] = "10.10.10.1",
        agent_type: str = "telemetry-agent",
        sensor_ctl_path: str = "/usr/libexec/redborder-sensors/sensor-ctl.sh",
        extra_args: str = "",
    ) -> CommandResult:
        """Starts a sandboxed mock sensor using redborder-sensors sensor-ctl.sh.

        Example:
            sensor-ctl start flow1 --ip 10.10.10.2 telemetry-agent -target 10.10.10.1
            sensor-ctl start snmp1 --ip 10.10.10.4 snmp
        """
        quoted_path = shlex.quote(sensor_ctl_path)
        cmd = f"{quoted_path} start {shlex.quote(name)} --ip {shlex.quote(ip)} {shlex.quote(agent_type)}"
        if target_ip and agent_type != "snmp":
            cmd = f"{cmd} -target {shlex.quote(target_ip)}"
        if extra_args:
            cmd = f"{cmd} {extra_args}"
        return self.run(cmd, timeout=30)

    def stop_mock_sensor(
        self,
        name: str = "flow1",
        sensor_ctl_path: str = "/usr/libexec/redborder-sensors/sensor-ctl.sh",
    ) -> CommandResult:
        """Stops and cleans up a sandboxed mock sensor."""
        quoted_path = shlex.quote(sensor_ctl_path)
        safe_name = shlex.quote(name)
        return self.run(f"{quoted_path} stop {safe_name}", timeout=30)

    def list_mock_sensors(
        self,
        sensor_ctl_path: str = "/usr/libexec/redborder-sensors/sensor-ctl.sh",
    ) -> str:
        """Lists currently running mock sensors."""
        quoted_path = shlex.quote(sensor_ctl_path)
        res = self.run(f"{quoted_path} list", timeout=15)
        return res.stdout

    def is_mock_sensor_running(
        self,
        name: str = "flow1",
        sensor_ctl_path: str = "/usr/libexec/redborder-sensors/sensor-ctl.sh",
    ) -> bool:
        """Checks if a mock sensor is actively listed as Running."""
        output = self.list_mock_sensors(sensor_ctl_path)
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] == name:
                return parts[3].lower() == "running"
        return False

    def start_mock_webserver(
        self,
        name: str = "rb-web",
        ip: str = "10.10.10.50",
        config_name: str = "config.json",
        sensor_ctl_path: str = "/usr/libexec/redborder-sensors/sensor-ctl.sh",
    ) -> CommandResult:
        """Starts a sandboxed mock webserver using redborder-sensors sensor-ctl.sh."""
        quoted_path = shlex.quote(sensor_ctl_path)
        cmd = f"{quoted_path} start {shlex.quote(name)} --ip {shlex.quote(ip)} webserver"
        if config_name and config_name != "config.json":
            cmd = f"{cmd} -config /usr/libexec/redborder-sensors/configs/webserver/{shlex.quote(config_name)}"
        return self.run(cmd, timeout=30)

    def stop_mock_webserver(
        self,
        name: str = "rb-web",
        sensor_ctl_path: str = "/usr/libexec/redborder-sensors/sensor-ctl.sh",
    ) -> CommandResult:
        """Stops and cleans up a sandboxed mock webserver."""
        return self.stop_mock_sensor(name=name, sensor_ctl_path=sensor_ctl_path)

    def start_all_baseline_mock_sandboxes(self) -> None:
        """Starts all baseline mock sensor sandboxes (Flow, Vault, SNMP, HTTP Webserver)
        on the test subnet 10.10.10.0/24 so network devices and routes settle before Web UI operations.
        """
        # Flow generator (10.10.10.2 -> 10.10.10.1)
        if not self.is_mock_sensor_running("rb-flow"):
            self.start_mock_sensor(name="rb-flow", ip="10.10.10.2", target_ip="10.10.10.1", agent_type="telemetry-agent")

        # Vault syslog generator (10.10.10.3 -> 10.10.10.1)
        if not self.is_mock_sensor_running("rb-vault"):
            self.start_mock_sensor(
                name="rb-vault",
                ip="10.10.10.3",
                target_ip="10.10.10.1",
                agent_type="telemetry-agent",
                extra_args="-mode syslog -port 514 -rate 5",
            )

        # SNMP mock agent (10.10.10.4)
        if not self.is_mock_sensor_running("rb-snmp"):
            self.start_mock_sensor(name="rb-snmp", ip="10.10.10.4", agent_type="snmp")

        # HTTP mock webserver (10.10.10.50)
        if not self.is_mock_sensor_running("rb-web"):
            self.start_mock_webserver(name="rb-web", ip="10.10.10.50")

    def stop_all_baseline_mock_sandboxes(self) -> None:
        """Stops and cleans up all baseline mock sandboxes."""
        for name in ["rb-flow", "rb-vault", "rb-snmp", "rb-web"]:
            try:
                self.stop_mock_sensor(name=name)
            except Exception:
                pass

    def run_http_agent_check(
        self,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        auth_type: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        follow_redirects: bool = False,
        timeout: int = 15,
        script_path: str = "/usr/lib/redborder/scripts/rb_http_agent.rb",
    ) -> CommandResult:
        """Runs the Redborder rb_http_agent.rb CLI script to check an HTTP endpoint."""
        cmd_parts = [
            shlex.quote(script_path),
            "-u", shlex.quote(url),
            "-X", shlex.quote(method.upper()),
            "-s", str(expected_status),
            "--timeout", str(timeout),
        ]
        if follow_redirects:
            cmd_parts.append("-L")
        if auth_type and auth_type.lower() == "basic" and username and password:
            cmd_parts.extend(["-a", "basic", "-U", shlex.quote(username), "-P", shlex.quote(password)])
        if headers:
            headers_json = json.dumps(headers)
            cmd_parts.extend(["-H", shlex.quote(headers_json)])
        if body:
            cmd_parts.extend(["-d", shlex.quote(body)])

        cmd = " ".join(cmd_parts)
        return self.run(cmd, timeout=timeout + 5)


    def get_chef_node_list(self) -> List[str]:
        """Returns the list of all node names currently registered in Chef Infra Server."""
        res = self.run("knife node list 2>/dev/null", timeout=30)
        if not res.ok or not res.stdout.strip():
            return []
        nodes = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("INFO:") and not line.startswith("WARN:"):
                nodes.append(line)
        return nodes

    def get_rails_sensor_ids(self) -> Set[int]:
        """Queries Redborder Rails database for all active sensor IDs."""
        cmd = (
            "bash -c 'source /etc/profile && rvm use ruby-3.4.11@web &>/dev/null && "
            "cd /var/www/rb-rails && bundle exec bin/rails runner \"puts Sensor.pluck(:id).inspect\" 2>/dev/null'"
        )
        res = self.run(cmd, timeout=30)
        if not res.ok or not res.stdout.strip():
            return set()
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, list):
                        return {int(x) for x in parsed if isinstance(x, (int, str)) and str(x).isdigit()}
                except Exception:
                    pass
        return set()

    def find_orphaned_chef_nodes(self) -> List[Dict[str, Any]]:
        """Audits Chef Server nodes against active Rails sensors to detect orphaned nodes.

        Ignores known non-sensor system nodes: appliance hostname, 'cep'.
        Identifies any sensor node ('rbvault-<id>', 'rbflow-<id>', 'rbsnmp-<id>', 'rBsensor-<id>',
        'rbproxy-<id>') whose sensor ID does not exist in the Rails database.
        """
        chef_nodes = self.get_chef_node_list()
        rails_sensor_ids = self.get_rails_sensor_ids()
        orphans = []

        system_node_prefixes = ("cep",)

        for node_name in chef_nodes:
            # Skip system / cluster nodes
            if node_name in system_node_prefixes or node_name.startswith("rb-dvanhoucke") or node_name.startswith("rb-manager"):
                continue

            # Check if this node is a sensor node
            # Patterns: rbvault-<id>, rbflow-<id>, rbsnmp-<id>, rBsensor-<id>, rbproxy-<id>
            match = re.match(r"^(?:rbvault|rbflow|rbsnmp|rBsensor|rbproxy)-(\d+)$", node_name, re.IGNORECASE)
            if match:
                sensor_id = int(match.group(1))
                if sensor_id not in rails_sensor_ids:
                    # Query knife for details on this orphaned node
                    show_res = self.run(f"knife node show {shlex.quote(node_name)} -F json 2>/dev/null", timeout=15)
                    node_data = {}
                    ip = None
                    rbname = None
                    if show_res.ok and show_res.stdout.strip():
                        try:
                            # Strip any knife header lines (e.g. INFO: Using configuration...)
                            raw_json = "\n".join(
                                l for l in show_res.stdout.splitlines()
                                if not l.startswith("INFO:") and not l.startswith("WARN:")
                            )
                            node_data = json.loads(raw_json)
                            normal = node_data.get("normal", {})
                            default = node_data.get("default", {})
                            override = node_data.get("override", {})

                            # Search normal -> default -> override -> top-level
                            ip = (
                                normal.get("ipaddress")
                                or normal.get("redborder", {}).get("sensor", {}).get("ip")
                                or normal.get("redborder", {}).get("ipaddress")
                                or default.get("ipaddress")
                                or default.get("redborder", {}).get("sensor", {}).get("ip")
                                or default.get("redborder", {}).get("ipaddress")
                                or override.get("ipaddress")
                                or override.get("redborder", {}).get("sensor", {}).get("ip")
                                or node_data.get("ipaddress")
                            )
                            rbname = (
                                normal.get("rbname")
                                or normal.get("redborder", {}).get("sensor", {}).get("rbname")
                                or default.get("rbname")
                                or default.get("redborder", {}).get("sensor", {}).get("rbname")
                                or override.get("rbname")
                                or node_data.get("name")
                            )
                        except Exception:
                            pass
                    orphans.append({
                        "node_name": node_name,
                        "sensor_id": sensor_id,
                        "ip": ip,
                        "rbname": rbname,
                    })

        return orphans

    def cleanup_orphaned_chef_nodes(self, ip: Optional[str] = None) -> List[str]:
        """Checks for and removes any orphaned Chef nodes for a given IP or unassociated sensor, returning warnings."""
        cleaned = []
        if not ip:
            return cleaned

        safe_ip = ip.replace("'", "\\'")
        search_cmd = f"knife search node 'ipaddress:{safe_ip}' -a name -F json 2>/dev/null"
        res = self.run(search_cmd, timeout=30)
        if not res.ok or not res.stdout.strip():
            return cleaned

        try:
            data = json.loads(res.stdout)
            # data can be {"results": N, "rows": [{"name": "..."}, ...]} OR {"rows": [{"node_key": {"name": "..."}}]}
            rows = data.get("rows", [])
            for row in rows:
                node_name = None
                if isinstance(row, dict):
                    if "name" in row:
                        node_name = row["name"]
                    else:
                        for k, v in row.items():
                            if isinstance(v, dict) and "name" in v:
                                node_name = v["name"]
                                break
                            elif isinstance(k, str) and not k.startswith("http"):
                                node_name = k
                                break
                if node_name:
                    import warnings
                    warn_msg = f"[Self-Healing Warning] Found orphaned Chef node '{node_name}' registered with IP {ip}. Deleting it to prevent stale rsyslog/pipeline routes."
                    warnings.warn(warn_msg, UserWarning)
                    print(f"\n{warn_msg}")
                    self.run(f"knife node delete {shlex.quote(node_name)} -y 2>/dev/null", timeout=15)
                    self.run(f"knife client delete {shlex.quote(node_name)} -y 2>/dev/null", timeout=15)
                    cleaned.append(node_name)
        except Exception:
            pass
        return cleaned

    def is_druid_ready(self, port: int = 8888) -> bool:
        """Checks if Druid router/broker HTTP health check responds with 200 OK and true."""
        cmd = f"curl -s -i http://localhost:{port}/status/health || curl -s -i http://localhost:8082/status/health"
        res = self.run(cmd, timeout=10)
        return res.ok and ("200 OK" in res.stdout or "true" in res.stdout.strip().lower())

    def wait_for_druid_ready(self, timeout: int = 60, interval: float = 3.0, port: int = 8888) -> bool:
        """Polls Druid health check until it is healthy and ready to accept queries.

        Useful after Namespace additions or deletions which trigger Druid restarts.
        """
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self.is_druid_ready(port=port):
                return True
            time.sleep(interval)
        return False

    def execute_druid_sql(
        self,
        query_sql: str,
        port: int = 8082,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> Optional[List[Dict[str, Any]]]:
        """Executes a Druid SQL query via curl with retry logic for transient Druid restarts."""
        import time

        payload = json.dumps({"query": query_sql})
        curl_cmd = (
            f"echo {shlex.quote(payload)} | "
            f"curl -s --max-time 10 -X POST -H 'Content-Type: application/json' "
            f"-d @- http://localhost:{port}/druid/v2/sql"
        )
        for attempt in range(max_retries):
            try:
                res = self.run(curl_cmd, timeout=15)
                if res.ok and res.stdout.strip():
                    data = json.loads(res.stdout)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
            # If Druid is restarting or recovering, wait briefly before next attempt
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        return None

    def run_chef_client(self, timeout: int = 120) -> CommandResult:
        """Runs chef-client on the target host to sync configurations."""
        return self.run("/usr/bin/chef-client --no-color", timeout=timeout)

    def converge_chef_and_wait_druid(
        self,
        iterations: int = 2,
        druid_timeout: int = 90,
        chef_timeout: int = 180,
    ) -> bool:
        """Runs chef-client to convergence and verifies Druid readiness.

        Useful during pre-phase / post-phase setup after domain tree modifications.
        """
        for i in range(max(1, iterations)):
            chef_res = self.run_chef_client(timeout=chef_timeout)
            if not chef_res.ok:
                return False
            if not self.wait_for_druid_ready(timeout=druid_timeout):
                return False
        return True

    def rebuild_sensor_tree(self) -> CommandResult:
        """Runs Rails runner to recalculate tree lft/rgt bounds via Sensor.rebuild!(false)."""
        cmd = (
            "bash -lc 'rvm use ruby-3.4.11@web && cd /var/www/rb-rails && "
            "RAILS_ENV=production bundle exec bin/rails runner \"Sensor.rebuild!(false)\"'"
        )
        return self.run(cmd, timeout=30)

    def sync_pending_incidents(self) -> CommandResult:
        """Runs UpdateContentIncidentsJob to process and make newly generated alarm incidents visible."""
        cmd = (
            "bash -lc 'rvm use ruby-3.4.11@web && cd /var/www/rb-rails && "
            "RAILS_ENV=production bundle exec bin/rails runner "
            "\"Redborder::Jobs::UpdateContentIncidentsJob.new(false, 1).perform\"'"
        )
        return self.run(cmd, timeout=30)

    def get_druid_tables(self, prefix: str, port: int = 8082) -> List[str]:
        """Discovers all active Druid table names for a given datasource prefix (e.g. 'rb_flow', 'rb_vault', 'rb_monitor')
        including base tables and namespace partitioned tables (e.g. rb_vault_<namespace_uuid>).
        """
        sql = f"SELECT distinct TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'druid' AND (TABLE_NAME = '{prefix}' OR TABLE_NAME LIKE '{prefix}_%')"
        rows = self.execute_druid_sql(sql, port=port)
        tables = []
        if rows:
            for r in rows:
                name = r.get("TABLE_NAME")
                if name:
                    tables.append(name)
        return tables if tables else [prefix]

    def _get_druid_tables(self, prefix: str, port: int = 8082) -> List[str]:
        """Alias for get_druid_tables for backward compatibility."""
        return self.get_druid_tables(prefix, port=port)

    def query_druid_flow_count(
        self,
        sensor_name: Optional[str] = None,
        sensor_ip: Optional[str] = None,
        port: int = 8082,
    ) -> int:
        """Queries Druid SQL for the total number of flow events across rb_flow tables, optionally filtered by sensor_name and/or sensor_ip."""
        clauses = []
        if sensor_name:
            safe_name = sensor_name.replace("'", "''")
            clauses.append(f"sensor_name = '{safe_name}'")
        if sensor_ip:
            safe_ip = sensor_ip.replace("'", "''")
            clauses.append(f"sensor_ip = '{safe_ip}'")

        where_str = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        tables = self._get_druid_tables("rb_flow", port=port)
        total_count = 0
        for tbl in tables:
            query_sql = f'SELECT count(*) as total FROM "{tbl}"{where_str}'
            data = self.execute_druid_sql(query_sql, port=port)
            if data and len(data) > 0 and "total" in data[0]:
                try:
                    total_count += int(data[0]["total"])
                except (ValueError, TypeError):
                    pass
        return total_count

    def query_druid_sensor_flows(
        self,
        sensor_name: str,
        limit: int = 5,
        port: int = 8082,
    ) -> List[Dict[str, Any]]:
        """Retrieves recent sample flow records from Druid for a given sensor_name."""
        safe_name = sensor_name.replace("'", "''")
        safe_limit = max(1, min(int(limit), 100))
        tables = self._get_druid_tables("rb_flow", port=port)
        for tbl in tables:
            query_sql = (
                f'SELECT __time, sensor_name, sensor_ip, sum_pkts, sum_bytes '
                f'FROM "{tbl}" WHERE sensor_name = \'{safe_name}\' '
                f'ORDER BY __time DESC LIMIT {safe_limit}'
            )
            data = self.execute_druid_sql(query_sql, port=port)
            if data:
                return data
        return []

    def query_druid_vault_count(
        self,
        sensor_name: Optional[str] = None,
        sensor_ip: Optional[str] = None,
        port: int = 8082,
    ) -> int:
        """Queries Druid SQL for the total number of syslog events across rb_vault tables.

        Note: in rb_vault schema, the sender IP column is named 'fromhost_ip'.
        """
        clauses = []
        if sensor_name:
            safe_name = sensor_name.replace("'", "''")
            clauses.append(f"sensor_name = '{safe_name}'")
        if sensor_ip:
            safe_ip = sensor_ip.replace("'", "''")
            clauses.append(f"fromhost_ip = '{safe_ip}'")

        where_str = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        tables = self._get_druid_tables("rb_vault", port=port)
        total_count = 0
        for tbl in tables:
            query_sql = f'SELECT count(*) as total FROM "{tbl}"{where_str}'
            data = self.execute_druid_sql(query_sql, port=port)
            if data and len(data) > 0 and "total" in data[0]:
                try:
                    total_count += int(data[0]["total"])
                except (ValueError, TypeError):
                    pass
        return total_count

    def query_druid_sensor_vault_logs(
        self,
        sensor_name: str,
        limit: int = 5,
        port: int = 8082,
    ) -> List[Dict[str, Any]]:
        """Retrieves recent sample syslog records from Druid rb_vault for a given sensor_name."""
        safe_name = sensor_name.replace("'", "''")
        safe_limit = max(1, min(int(limit), 100))
        tables = self._get_druid_tables("rb_vault", port=port)
        for tbl in tables:
            query_sql = (
                f'SELECT __time, sensor_name, fromhost_ip, message, app_name, hostname '
                f'FROM "{tbl}" WHERE sensor_name = \'{safe_name}\' '
                f'ORDER BY __time DESC LIMIT {safe_limit}'
            )
            data = self.execute_druid_sql(query_sql, port=port)
            if data:
                return data
        return []

    def query_druid_monitor_count(
        self,
        sensor_name: Optional[str] = None,
        monitor: Optional[str] = None,
        port: int = 8082,
    ) -> int:
        """Queries Druid SQL for the total number of monitor events across rb_monitor tables."""
        clauses = []
        if sensor_name:
            safe_name = sensor_name.replace("'", "''")
            clauses.append(f"sensor_name = '{safe_name}'")
        if monitor:
            safe_mon = monitor.replace("'", "''")
            clauses.append(f"\"monitor\" = '{safe_mon}'")

        where_str = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        tables = self._get_druid_tables("rb_monitor", port=port)
        total_count = 0
        for tbl in tables:
            query_sql = f'SELECT count(*) as total FROM "{tbl}"{where_str}'
            data = self.execute_druid_sql(query_sql, port=port)
            if data and len(data) > 0 and "total" in data[0]:
                try:
                    total_count += int(data[0]["total"])
                except (ValueError, TypeError):
                    pass
        return total_count

    def query_druid_sensor_monitor_records(
        self,
        sensor_name: str,
        monitor: str = "cpu",
        limit: int = 5,
        port: int = 8082,
    ) -> List[Dict[str, Any]]:
        """Retrieves recent sample monitor records from Druid rb_monitor."""
        safe_name = sensor_name.replace("'", "''")
        safe_mon = monitor.replace("'", "''")
        safe_limit = max(1, min(int(limit), 100))
        tables = self._get_druid_tables("rb_monitor", port=port)
        for tbl in tables:
            query_sql = (
                f'SELECT __time, sensor_name, "monitor", "name", sum_value '
                f'FROM "{tbl}" WHERE sensor_name = \'{safe_name}\' AND "monitor" = \'{safe_mon}\' '
                f'ORDER BY __time DESC LIMIT {safe_limit}'
            )
            data = self.execute_druid_sql(query_sql, port=port)
            if data:
                return data
        return []

    def snmpwalk_query(
        self,
        target_ip: str,
        community: str = "public",
        version: str = "2c",
        oid: str = "1.3.6.1.2.1.1.1.0",
        timeout: int = 15,
    ) -> CommandResult:
        """Runs snmpwalk from the target host against a given IP and OID."""
        cmd = (
            f"snmpwalk -v {shlex.quote(version)} -c {shlex.quote(community)} "
            f"{shlex.quote(target_ip)} {shlex.quote(oid)}"
        )
        return self.run(cmd, timeout=timeout)
