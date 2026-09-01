# Forward compatibility

Support for third-party packages shipping their own probes has not been built yet, but
the design allows for it. Pattern keys use a `namespace:name` format and are stored in a
flat `{key: count}` JSON field. The server does not validate pattern keys against a
known vocabulary, so a new namespace requires no server release and no migration. This
behaviour is covered by a test in `tests/ingest/`, so that adding such validation later
will cause a visible failure rather than silently discarding data.

Every payload also includes `probe_sources`, which records the packages that supplied
probes and their versions. Without it, a count of zero would be ambiguous: the pattern
might be absent, or nothing might have looked for it.

Display metadata for patterns, such as labels, descriptions, and documentation links,
belongs in a server-side registry that submissions do not reference when they are
written. Storing submissions first and describing them later keeps the ingest endpoint
from becoming a coordination point between the server and every probe author.
