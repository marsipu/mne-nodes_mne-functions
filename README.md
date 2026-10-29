# mne-nodes_mne-functions

This is a plugin for [mne-nodes](https://github.com/marsipu/mne-nodes), which contains all functions and instantiatable classes from [mne-python](https://github.com/mne-tools/mne-python). It uses an automatic scraper to generate the configuration-file.

> **Caution:** This is mainly used to expand capabilities of [mne-nodes](https://github.com/marsipu/mne-nodes). Some nodes might not work. The configuration is generated automatically from [mne-python](https://github.com/mne-tools/mne-python) and may change when the upstream package is updated.

## Install and load

Run `python -m pip install .` (or `python -m pip install -e .` for development).
In mne-nodes, choose **Plugins > Load Installed Plugin...** and select
`mne_functions`. Installation alone does not activate the plugin.
For local loading without installation, select
`src/mne_nodes_mne_functions/mne_functions_config.json` using
**Plugins > Load Plugin from Path**.

## Package structure and publishing

Runtime Python modules and JSON resources live in `src/mne_nodes_mne_functions/`.
The root contains `pyproject.toml`, `README.md` and the BSD-3-Clause `LICENSE`.
Wheels and source distributions explicitly include the package and its resources.
Versioning uses Git tags via Hatch-VCS, with a fallback for untagged source copies;
source distributions retain the built version when rebuilt without Git.

```shell
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

Review the version, dependencies, licensing and package-index name before release.
After moving an existing checkout to this layout, reinstall editable installations
and restart mne-nodes.
