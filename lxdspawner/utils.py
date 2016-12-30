import math
import re
import subprocess
import time

import pylxd

unit_file_template = """\
[Unit]
Description=jupyterhub-singleuser

[Service]
Type=simple
ExecStart={}
EnvironmentFile=/etc/jupyterhub-singleuser-environment

[Install]
WantedBy=multi-user.target
"""

cloud_config = """\
#cloud-config
bootcmd:
 - systemctl daemon-reload
 - systemctl enable jupyterhub-singleuser.service
runcmd:
 - systemctl start jupyterhub-singleuser.service
"""

def start(client,
          container_name,
          cmd,
          env,
          start_timeout,
          cpu_limit,
          mem_limit):
    """
    start starts a LXD container running the jupyterhub-singleuser program.
    """

    config = {
        # Inject cloud-config to enable/start the systemd unit.
        "user.user-data": cloud_config,
    }

    # Set cpu/mem limits.
    config['limits.memory'] = mem_limit
    config['limits.cpu'] = "{}".format(math.ceil(cpu_limit))
    if cpu_limit < 1:
        config['limits.cpu.allowance'] = "{}%".format(cpu_limit * 100)

    # TODO(axw) make arch and profiles configurable
    container = client.containers.create({
        'name': container_name,
        'config': config,
        'source': {
            'type': 'image',
            # TODO(axw) make image alias configurable,
            # or use configurable properties.
            #
            # TODO(axw) make it possible to use remote
            # image source
            'alias': 'jupyterhub/singleuser',
        },
    }, wait=True)

    cmd[0] = "/usr/local/bin/jupyterhub-singleuser"
    exec_start = subprocess.list2cmdline(cmd)
    env_file = "\n".join("{}={}".format(k, v) for (k, v) in env.items())
    unit_file = unit_file_template.format(exec_start)
    container.files.put("/etc/jupyterhub-singleuser-environment", env_file)
    container.files.put("/etc/systemd/system/jupyterhub-singleuser.service", unit_file)
    container.start()

    # Wait for the single-user process to be running, which implies that the
    # container has a network address assigned.
    for i in range(start_timeout):
        running = poll()
        if running is None:
            addr = _container_addr(container)
            port = 1234 # XXX
            return addr, port
            #return self.user.server.ip, self.user.server.port
        time.sleep(1)
    return None

def stop(client, container_name):
    """
    stop stops and removes the container with the given name.
    """
    try:
        container = client.containers.get(container_name)
    except pylxd.exceptions.NotFound:
        # No container, nothing to do.
        return
    if container.status == 'Running':
        container.stop(wait=True)
        container.delete(wait=True)

_systemctl_status_status_re = re.compile("status=[0-9]+(?:/[^)]+)")

def poll(client, container_name):
    """
    poll checks if the jupyterhub-singleuser program is running.
    """
    try:
        container = client.containers.get(container_name)
    except pylxd.exceptions.NotFound:
        return 0 # No container => process not running.
    if container.status != 'Running':
        return 0 # Container not running => process not running.
    res = container.execute(["/bin/systemctl", "is-active", "jupyterhub-singleuser"])
    status = res.stdout.rstrip()
    if status == "active":
        return None
    elif status == "inactive":
        return 0
    # The process failed, so parse the output of
    # "systemctl status" to get the exit code.
    res = container.execute(["/bin/systemctl", "status", "jupyterhub-singleuser"])
    line = res.stdout.split("Main PID:")[1].split("\n")[0]
    match = _systemctl_status_status_re.match(line)
    if match is None:
        # Could not parse the output, so return 0 as per the guidelines.
        return 0
    return int(match.group(1))


def _container_addr(container):
    st = container.state()
    assert st.status == 'Running'
    addresses = st.network['eth0']['addresses']
    for a in addresses:
        if a['scope'] == 'global' and a['family'] == 'inet':
            return a['address']
    raise ValueError("no global inet address found")
