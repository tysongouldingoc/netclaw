# EVE-NG Troubleshooting Notes

## Lab start fails with `network_name already in use`

Meaning:
- stale runtime bridges or tap interfaces still exist on the host
- the saved `.unl` file may be fine

Check:

```bash
ip link show | grep -E 'vnet|vunl|pnet'
ps -ef | grep -E 'qemu-system|dynamips|vpcs' | grep -v grep
sed -n '1,200p' /opt/unetlab/data/Logs/unl_wrapper.txt
```

Recommended response:
1. confirm the affected nodes are actually stopped
2. inspect stale `vnet*` and `vunl*` interfaces
3. clean up only what belongs to the failed lab, or restart the relevant EVE services if change policy allows
4. retry the start and re-check node processes

## Lab looks stopped but restart still fails

Possible cause:
- UI state and host runtime state disagree

Check:

```bash
ps -ef | grep -E 'qemu-system|dynamips|vpcs' | grep -v grep
ip link show | grep -E 'vnet|vunl|pnet'
ss -ltnp | grep -E '3276[0-9]|3277[0-9]|3278[0-9]'
```

## Web UI appears down

Check:

```bash
systemctl is-active apache2 mysql mariadb guacd docker tomcat9
ss -ltnp | grep -E ':(80|443) '
```

Interpretation:
- Apache on `80` usually means basic UI is up
- missing `443` means HTTPS is not listening
- inactive MySQL or MariaDB can break login and inventory behavior

## Direct neighbors do not form adjacency even though interfaces are up

Work from evidence in this order:
1. `.unl` interface-to-network bindings
2. host bridge membership (`vnet*`, `vunl*`)
3. guest interface names from CLI
4. protocol discovery such as CDP or LLDP

Check:

```bash
sed -n '1,220p' /opt/unetlab/labs/<lab>.unl
brctl show
ip -o link show | grep -E 'vnet|vunl'
```

Do not call a port mapping confirmed unless saved topology, host runtime state, and guest evidence agree.

## Image mismatch or missing image

Symptoms:
- node start exits quickly
- wrapper log mentions image or template failure

Check:

```bash
find /opt/unetlab/addons/qemu -maxdepth 2 -type d | sort
find /opt/unetlab/addons/iol/bin -maxdepth 1 -type f | sort
sed -n '1,220p' /opt/unetlab/html/templates/intel/<template>.yml
```

## Token-efficiency reminder

When troubleshooting through the console, prefer short targeted commands over long blanket outputs. Large routing tables and full running configs add tokens fast.
