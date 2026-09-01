# Third-party probe packages

Support for third-party packages shipping their own probes has not been built yet, but
the design allows for it.

Pattern keys use a `namespace:name` format and are stored in a flat `{key: count}` JSON
field. The server does not validate pattern keys against a known vocabulary, so a new
namespace requires no server release and no migration.

`probe_sources` records which probe packages ran during a scan, separate from the
`{key: count}` payload. Without it, the server can't tell whether a pattern key is
absent because it wasn't found or because the probe that reports it wasn't installed.

Display metadata — a pattern key's label, description, and category — lives in a
server-side registry, not in the submission. That lets us fix a typo or reclassify a
pattern without asking every project to resubmit.
