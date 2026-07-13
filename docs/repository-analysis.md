# Repository analysis artifacts

`.understand-anything/knowledge-graph.json` and `.understand-anything/meta.json`
are the canonical checked-in analysis outputs. Intermediate scans and tool trash
are disposable and ignored by Git; they must not be used as application inputs
or included in releases. Existing historical trash is retained until the
repository's normal cleanup process can remove it.
