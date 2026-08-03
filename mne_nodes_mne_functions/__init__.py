from importlib.resources import files

PLUGIN_NAME = "mne-functions"
PLUGIN_GITHUB = "https://github.com/marsipu/mne-nodes_mne-functions"
CONFIG_PATH = files(__package__) / "mne_functions_config.json"
SCRIPT_PATH = None