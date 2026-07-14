# Plugin Development Workspace

Use this directory to develop new plugins before migrating them to the marketplace.

## Workflow

1. Create your plugin here: `tokenade/plugins/my-plugin/`
2. Test it locally
3. Migrate to marketplace: `cp -r tokenade/plugins/my-plugin/ ~/Projects/tokenade-plugins/plugins/`
4. Remove from dev workspace: `rm -rf tokenade/plugins/my-plugin/`

## Structure

```
my-plugin/
├── plugin.py          # Plugin implementation
├── plugin.json        # Manifest
└── site_config.json   # Optional site config
```
