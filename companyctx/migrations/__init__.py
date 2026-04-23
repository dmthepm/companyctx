"""Numbered SQL migrations for the SQLite cache.

Migrations are discovered by filename pattern ``NNNN_<slug>.sql`` where
``NNNN`` is a zero-padded integer. The runner in :mod:`companyctx.cache`
applies every migration with a number greater than the value stored in the
``schema_version`` table, in ascending order, each inside its own
transaction. There are no implicit ``ALTER TABLE`` statements at startup —
every schema change is a numbered file landed alongside the code that
expects it.

Reference: COX-6 / GitHub #9.
"""
