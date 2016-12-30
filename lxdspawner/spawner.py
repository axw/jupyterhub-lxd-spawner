from traitlets import Unicode

import pylxd
from jupyterhub.spawner import Spawner
from tornado import gen

from lxdspawner import utils

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
        'jupyterhub-singleuser-{username}',
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
        return utils.start(
            self.client,
            self.container_name,
            cmd,
            self.get_env(),
            self.start_timeout,
            self.cpu_limit,
            self.mem_limit,
        )

        #self.ip = addr
        #self.port = port
        #self.db.commit()
        return addr, port

    @gen.coroutine
    def stop(self):
        utils.stop(self.client, self.container_name)

    @gen.coroutine
    def poll(self):
        return utils.poll(self.client, self.container_name)

