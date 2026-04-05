# Shipping

## Minimum Manifest

Your plugin should have a `pyproject.toml` like this at repo root:

```toml
[project]
name = "my_plugin"
version = "0.1.0"
description = "A starter LichtFeld Studio plugin"
readme = "README.md"
requires-python = ">=3.12"
authors = [
    { name = "Your Name" },
]

[tool.lichtfeld]
hot_reload = true
plugin_api = ">=1,<2"
lichtfeld_version = ">=0.4.2"
required_features = []
```

## Before You Publish

- Replace `my_plugin` with your real plugin id
- Replace `My Plugin` with your real panel title
- Rewrite the template `README.md`
- Add your own license choice for the plugin repo
- Validate the plugin with the local LFS validator
- Make the repo public if you want GitHub-url install or marketplace review

## GitHub Install

Once the plugin repo is public, users can install it directly from LFS with:

```python
import lichtfeld as lf

lf.plugins.install("https://github.com/owner/repo")
```

Using a tag is better for release testing:

```python
lf.plugins.install("https://github.com/owner/repo@v0.1.0")
```

## Recommended Release Steps

1. Commit the repo-root plugin.
2. Push `main`.
3. Tag a release like `v0.1.0`.
4. Validate the GitHub tarball path.
5. Only then ask users or maintainers to install from GitHub.
