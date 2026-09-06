# Architecture layers

Hard dependency direction for `plyunit`:

```text
common  →  (stdlib / numpy only)
core    →  common
engine  →  core, common
integrations → engine, core, common
api     →  re-exports only (no business logic)
```

| Layer | May import | Must not import |
| --- | --- | --- |
| `common` | stdlib, numpy | `core`, `engine`, `integrations` |
| `core` | `common`, `core.*` | `engine.*`, `integrations.*` |
| `engine` | `common`, `core` | `integrations.*` |
| `integrations` | `common`, `core`, `engine` | reverse |
| `api` | re-export maps | no business logic |

Composition root: `plyunit.backends.integrations.init` wires raylib/physics strategies into engine services.

Guards: `tests/common/test_import_boundaries.py`.
