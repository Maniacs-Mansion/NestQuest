"""NestQuest API service.

A standalone FastAPI deployable that owns the NestQuest database and
exposes it over HTTP to the Home Assistant integration (panel plane) and
the admin PWA (admin plane).  See Feature 16 (task cd03735b) in the
project tracker for the full contract.

This package imports the NestQuest domain ``core`` WITHOUT executing
``custom_components/nestquest/__init__.py`` — that parent package's
``__init__.py`` imports ``homeassistant``, which is absent from the
API's runtime.  The coupling is encapsulated in
:mod:`api.nestquest_core` (a ``sys.path`` bootstrap that makes ``core``
importable as a top-level package).  It is a TRANSITIONAL coupling that
Feature 18 will revisit: once the integration becomes a thin API client
and ``core`` moves out of the integration bundle, this helper goes away.
"""
from __future__ import annotations
