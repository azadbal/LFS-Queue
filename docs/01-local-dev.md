# Local Development

## Repo-Root Rule

If you want an LFS plugin to install directly from GitHub, the repo root itself must be the plugin root.

That means the plugin repo root should contain:

- `pyproject.toml`
- `__init__.py`
- `panels/`

Do not bury the plugin under a nested subfolder if GitHub install is part of the plan.

## Local Install Path

LFS discovers user plugins from:

```text
%USERPROFILE%\.lichtfeld\plugins\
```

Recommended Windows workflow:

```powershell
cmd /c mklink /J "$HOME\.lichtfeld\plugins\my_plugin" "C:\path\to\your\repo"
```

That keeps your local install and your git working tree on the same files.

## Discover, Load, Reload

These are separate:

- `discover()` finds installed plugins
- `load()` imports and activates one plugin
- `reload()` reloads an already-loaded plugin
- `load_all()` only auto-loads plugins whose `settings.json` contains `"load_on_startup": true`

If LFS is already open:

```python
import lichtfeld as lf

lf.plugins.discover()
lf.plugins.load("my_plugin")
lf.plugins.start_watcher()
```

## Startup Persistence

LFS does not infer startup loading from the manifest.

Startup loading happens only when the plugin has:

```json
{
  "load_on_startup": true
}
```

in:

```text
%USERPROFILE%\.lichtfeld\plugins\<plugin_name>\settings.json
```

This template ships that file on purpose so the starter plugin persists across launches.
