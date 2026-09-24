# Container image for the NestQuest API service (Feature 17).
#
# Build context is the REPOSITORY ROOT (compose sets it), because the
# API loads the bundled domain layer from
# custom_components/nestquest/core/ by file location
# (api/nestquest_core.py): the image must carry both api/ and the
# bundled core at their relative positions.  Everything else in the
# repository is excluded via .dockerignore.
#
# Multi-stage so no pip/build toolchain survives into the runtime:
# the builder installs the deployable's own manifest
# (api/requirements.txt) into a staging prefix and the runtime copies
# only the installed packages.  The service runs as a non-root user;
# the SQLite database lives on the mounted volume at
# /var/lib/nestquest (compose supplies NESTQUEST_DB_PATH pointing
# there — configuration is environment-supplied, never baked in).
#
# Both stages use the same base image pinned by digest, and
# api/requirements.txt pins exact versions, so a rebuild reproduces
# the deployed image instead of floating to whatever is newest.
FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS builder

COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt

FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

# The staged dependency install from the builder (no pip, no wheels).
COPY --from=builder /install /usr/local

# /app is the repository-root equivalent: api/ resolves imports as
# ``api.*`` and nestquest_core.py finds the bundled core one level up.
WORKDIR /app
COPY api/ ./api/
COPY custom_components/nestquest/core/ ./custom_components/nestquest/core/

# Non-root runtime user; owns the database volume mount point.
RUN useradd --system --create-home --home-dir /home/nestquest nestquest \
    && mkdir -p /var/lib/nestquest \
    && chown nestquest:nestquest /var/lib/nestquest
USER nestquest

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# The database path and the service token / OIDC settings are supplied
# by the environment (compose env_file), never committed into the image.
ENV NESTQUEST_DB_PATH=/var/lib/nestquest/nestquest.db
VOLUME /var/lib/nestquest

EXPOSE 8080
CMD ["uvicorn", "--factory", "api.app:create_app", "--host", "0.0.0.0", "--port", "8080"]
