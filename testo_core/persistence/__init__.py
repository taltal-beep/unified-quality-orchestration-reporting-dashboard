"""Engine-level persistence backends for plan results.

The orchestrator calls :meth:`PersistenceBackend.persist` after a plan
completes.  Two concrete backends ship with the package:

* :class:`JsonBackend` — writes ``plan_result.json`` to the artifacts tree.
* :class:`DbBackend` — upserts a :class:`~testo_core.repository.models.RunRecord`
  via the repository layer.

Both are best-effort: a failure to persist never fails the run.
"""

from testo_core.persistence.backend import PersistenceBackend
from testo_core.persistence.composite import composite_backend
from testo_core.persistence.db_backend import DbBackend
from testo_core.persistence.json_backend import JsonBackend

__all__ = [
    "PersistenceBackend",
    "JsonBackend",
    "DbBackend",
    "composite_backend",
]
