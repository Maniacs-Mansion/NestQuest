"""NestQuest storage layer.

A self-contained, Home-Assistant-free package holding the NestQuest
SQLite storage layer: schema DDL, the versioned migration runner, the
async connection wrapper, the path resolver, the domain constants and
recurrence model, and the typed DAOs.  Nothing in this package imports
``homeassistant``; the integration wires it into HA at its own layer
(constructing :class:`core.db.NestQuestDatabase` with an executor
adapter backed by ``hass.async_add_executor_job``).
"""
from __future__ import annotations
