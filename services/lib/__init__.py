"""Shared library: domain logic, data models, and integrations.

**Deployable** units stay at ``services/svc_*`` (see ``configs/product_services.yml``).
Everything import-only for workers and HTTP lives under ``services.lib.*``.

Layers (conceptual):

- **kernel** — ``core``, ``bus``, ``data_models``, ``observability``, ``audit``
- **knowledge** — ``ontology``, ``graph``
- **corpus** — ``ingestion``, ``parsers``, ``normalization``, ``ocr``, ``enrichment``, ``storage``
- **query-time** — ``indexing``, ``retrieval``, ``reranking``, ``generation``
- **quality** — ``evaluation``
"""
