# Watchlists

One file per platform listing the fields **your campaign tool sends**. The weekly
check only raises the alarm for changes to these fields (plus brand-new mandatory
fields, which break every platform push).

These start as a **standard set** of fields most campaign tools use. To make the
alerts more precise, edit them to match what your tool actually sends:

```yaml
levels:
  Campaign:
    displayName:                       # a field we fill in (any value)
    entityStatus: [ENTITY_STATUS_PAUSED, ENTITY_STATUS_ACTIVE]   # ...and the values we use
```

`version_in_use` is the API version your campaign tool calls today. When a new
version comes out and nothing on this list breaks, the weekly pull request
proposes changing it - merging that pull request is your approval.
