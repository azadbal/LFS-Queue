# Marketplace Submission

## Two Different Paths

There are two practical distribution paths today:

- Direct GitHub install from inside LFS
- Curated marketplace inclusion

Direct GitHub install does not require marketplace inclusion.

## Curated Marketplace Path

The best verified curated-list workflow is:

1. Make your plugin repo public and installable from its GitHub root.
2. Open a pull request against `MrNeRF/LichtFeld-Studio`.
3. Add your plugin repo URL to `src/python/lfs_plugins/marketplace.py` in `CURATED_PLUGIN_URLS`.
4. Include a short plugin summary and compatibility values in the PR body.

Useful PR metadata:

- `plugin_api = ">=1,<2"`
- `lichtfeld_version = ">=0.4.2"`
- one-line summary of what the plugin does

## Suggested PR Body

```text
This PR adds my LichtFeld Studio plugin to the curated marketplace list.

Plugin repo:
https://github.com/<owner>/<repo>

Summary:
<one-line summary>

Compatibility:
- plugin_api: >=1,<2
- lichtfeld_version: >=0.4.2

Requested change:
- Add https://github.com/<owner>/<repo> to CURATED_PLUGIN_URLS in src/python/lfs_plugins/marketplace.py
```

## Important Caveat

The registry-backed side of marketplace submission is still not documented publicly in a way that is as clear as the curated PR path. For now, the curated PR route is the strongest verified submission workflow.
