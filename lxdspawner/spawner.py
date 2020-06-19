from traitlets import Unicode

import math
import re
import subprocess
import time

import pylxd
from jupyterhub.spawner import Spawner
from tornado import gen

unit_file_template = """\
[Unit]
Description=jupyterhub-singleuser

[Service]
Type=simple
ExecStart={}
EnvironmentFile=/etc/jupyterhub-singleuser-environment
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu

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

def write_env(container, env):
    env_file = "\n".join("{}={}".format(k, v) for (k, v) in env.items())
    container.files.put("/etc/jupyterhub-singleuser-environment", env_file)

def launch(client,
          container_name,
          cmd,
          env,
          cpu_limit,
          mem_limit):
    config = {
        # Inject cloud-config to enable/start the systemd unit.
        "user.user-data": cloud_config,
    }

    # Set cpu/mem limits.
    config['limits.memory'] = mem_limit
    if cpu_limit is not None:
        config['limits.cpu'] = "{}".format(math.ceil(cpu_limit))
        if cpu_limit < 1:
            config['limits.cpu.allowance'] = "{}%".format(cpu_limit * 100)

    # TODO(axw) make arch and profiles configurable
    container = client.containers.create({
        'name': container_name,
        'config': config,
        'profiles': ['jupyterhub-singleuser-limits'],
        'source': {
            'type': 'image',
            # TODO(axw) make image alias configurable,
            # or use configurable properties.
            #
            # TODO(axw) make it possible to use remote
            # image source
            'alias': 'jupyterhub-singleuser',
        },
    }, wait=True)

    exec_start = subprocess.list2cmdline(cmd)
    unit_file = unit_file_template.format(exec_start)
    container.files.put("/etc/systemd/system/jupyterhub-singleuser.service", unit_file)
    write_env(container, env)
    return container

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
    # TODO: Below code is broken, should fix
    return 1
    ## The process failed, so parse the output of
    ## "systemctl status" to get the exit code.
    #res = container.execute(["/bin/systemctl", "status", "jupyterhub-singleuser"])
    #line = res.stdout.split("Main PID:")[1].split("\n")[0]
    #match = _systemctl_status_status_re.match(line)
    #if match is None:
    #    # Could not parse the output, so return 0 as per the guidelines.
    #    return 0
    #return int(match.group(1))

def query_container_addr(container):
    st = container.state()
    assert st.status == 'Running'
    addresses = st.network['eth0']['addresses']
    for a in addresses:
        if a['scope'] == 'global' and a['family'] == 'inet':
            return a['address']
    raise ValueError("no global inet address found")

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
    try:
        container = client.containers.get(container_name)
        write_env(container, env)
    except pylxd.exceptions.NotFound:
        container = launch(client, container_name, cmd, env, cpu_limit, mem_limit)

    if container.status == "Running":
        container.execute(["systemctl", "restart", "jupyterhub-singleuser"])
    else:
        container.start()

    # Wait for the single-user process to be running, which implies that the
    # container has a network address assigned.
    for i in range(start_timeout):
        running = poll(client, container_name)
        if running is None:
            addr = query_container_addr(container)

            return addr, 8888
        time.sleep(1)
    return None

class LXDSpawner(Spawner):
    lxd_endpoint = Unicode(
        config=True,
        help='Endpoint to use for LXD API calls'
    )

    lxd_client_cert = Unicode(
        config=True,
        help='Client certificate to use for authenticating LXD API calls'
    )

    lxd_client_key = Unicode(
        config=True,
        help='Client key to use for authenticating LXD API calls'
    )

    container_name_template = Unicode(
        'jupyterhub-singleuser-instance-{username}',
        config=True,
        help='Template for naming the LXD containers. {username} is expanded.'
    )

    def __init__(self, *args, **kwargs):
        super(LXDSpawner, self).__init__(*args, **kwargs)
        self.client = self._lxd_client()
        self.container_name = self._expand_user_vars(self.container_name_template)
        self.log.debug('user:%s Initialized spawner for container %s', self.user.name, self.container_name)

    def _expand_user_vars(self, s):
        """
        Expand user related variables in a given string
          {username} -> Name of the user
        """
        return s.format(username=self.user.name)

    def _lxd_client(self):
        """
        _lxd_client returns a client object to manage LXD containers.
        """
        # TODO(axw) this just gives a localhost conn, we'll need
        # to use configuration to get a remote conn.
        #
        # TODO(axw) obtain LXD server's CA cert so we can verify.
        kwargs = {'verify': False}
        if self.lxd_endpoint:
            kwargs['endpoint'] = self.lxd_endpoint
        if self.lxd_client_cert and self.lxd_client_key:
            kwargs['cert'] = (self.lxd_client_cert, self.lxd_client_key)
        return pylxd.Client(**kwargs)

    def load_state(self, state):
        super().load_state(state)
        container_name = state.get('container_name', None)
        if container_name:
            self.container_name = container_name

    def clear_state(self):
        super().clear_state()

    def get_state(self):
        state = super().get_state()
        if self.container_name:
            state['container_name'] = self.container_name
        return state

    @gen.coroutine
    def start(self):
        self.log.info("starting container {}".format(self.container_name))

        cmd = self.cmd[:]
        cmd.extend(self.get_args())
        cmd = list(filter(lambda opt: "--port=" not in opt, cmd))
        result = start(
            self.client,
            self.container_name,
            cmd,
            self.get_env(),
            self.start_timeout,
            self.cpu_limit,
            self.mem_limit
            )

        if result:
            self.ip = result[0]
            self.port = result[1]
            return (self.ip, self.port)

        return None

    @gen.coroutine
    def stop(self):
        try:
            container = self.client.containers.get(self.container_name)
        except pylxd.exceptions.NotFound:
            # No container, nothing to do.
            return
        if container.status == 'Running':
            container.stop(wait=True)

    @gen.coroutine
    def poll(self):
        return poll(self.client, self.container_name)

