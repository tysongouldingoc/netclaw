# EVE-NG Command Patterns

These are host-side checks that complement the MCP tools when the API, runtime bridges, or web UI behave unexpectedly.

## Platform checks

```bash
systemctl is-active apache2 mysql mariadb guacd docker tomcat9
systemctl --no-pager --type=service --state=running | grep -Ei 'apache|mysql|mariadb|guacd|docker|tomcat|eve|unetlab'
ss -ltnp | grep -E ':(80|443) '
```

## Lab file checks

```bash
find /opt/unetlab/labs -type f -name '*.unl' | sort
sed -n '1,220p' /opt/unetlab/labs/<path>/<lab>.unl
```

## Runtime ownership checks

```bash
ps -ef | grep -E 'qemu-system|dynamips|vpcs' | grep -v grep
ss -ltnp | grep -E '3276[0-9]|3277[0-9]|3278[0-9]'
ip link show | grep -E 'vnet|vunl|pnet'
brctl show
```

## Wrapper and platform logs

```bash
sed -n '1,200p' /opt/unetlab/data/Logs/unl_wrapper.txt
sed -n '1,200p' /opt/unetlab/data/Logs/error.txt
sed -n '1,200p' /opt/unetlab/data/Logs/php_errors.txt
```

## Image inventory checks

```bash
find /opt/unetlab/addons/qemu -maxdepth 2 -type d | sort
find /opt/unetlab/addons/iol/bin -maxdepth 1 -type f | sort
```

## Template inspection

```bash
sed -n '1,220p' /opt/unetlab/html/templates/intel/<template>.yml
```

## Validator check

```bash
python3 workspace/skills/eve-lab-topology-design/scripts/validate_unl_topology.py /path/to/lab.unl --verbose
```

## MCP-first preference

For normal lab operations, prefer the EVE MCP tools over ad-hoc shell parsing:
- lab inventory and metadata → `eve_list_labs`, `eve_get_lab`
- node state → `eve_list_nodes`, `eve_get_node`
- topology view → `eve_get_topology`, `eve_list_node_interfaces`
- config export → `eve_get_all_configs`
- live CLI → `eve_discover_node`, `eve_exec_*`
