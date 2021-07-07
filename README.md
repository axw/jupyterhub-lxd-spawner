# JupyterHub LXD Spawner for KeioAIConsortium

JupyterHub Spawner for LXD.

## Development

```bash
pipenv install
```

## Behaviors of functions

behaviors of functions and situations to be called

### launch

After logging in, if your container doesn't exist, this function will be called.

Container will be created and its status will be "stopped".

### start

After loggin in, usually this will be called.

If container already has started, restart it.

If container doesn't start, assign one gpu to it and start it.(If you want to know more details about gpu assignment program, refer to [Iris](https://github.com/KeioAIConsortium/iris) )

### poll

Check jupyterhub-singleuser program is runnning.

Only when the program is running, return None. Otherwise, return the number.

## short tips

### config

```python
iris_url = Unicode(
    config=True,
    help='Iris Application URL'
)
```

If you write something like this, you can get the config same as variable name.

```python
c.LXDSpawner.iris_url = 'http://iris'
```

In `jupyterhub_config.py`, configure as above.
