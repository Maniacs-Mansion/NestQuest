# Admin PWA image (Feature 24): builds the Vite bundle from admin/ and
# serves it with nginx.  Build context is the REPOSITORY ROOT (it needs
# admin/); deploy/pwa/Dockerfile.dockerignore limits that context to
# admin/ and this directory's nginx.conf.
#
#   docker compose -f deploy/compose.yaml build pwa
#
# The VITE_* values are baked into the bundle at build time.  None is a
# secret (the OIDC client is a public PKCE client), and all three are
# required: the build fails fast rather than relying on app defaults.

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build

ARG VITE_AUTHENTIK_CLIENT_ID
ARG VITE_AUTHENTIK_ISSUER
ARG VITE_API_BASE_URL

WORKDIR /src/admin
COPY admin/package.json admin/package-lock.json ./
RUN npm ci
COPY admin/ ./
RUN test -n "$VITE_AUTHENTIK_CLIENT_ID" && test -n "$VITE_AUTHENTIK_ISSUER" && test -n "$VITE_API_BASE_URL" \
    || { echo "VITE_AUTHENTIK_CLIENT_ID, VITE_AUTHENTIK_ISSUER and VITE_API_BASE_URL build args are required" >&2; exit 1; }
RUN npm run build

FROM nginx:alpine@sha256:1ed1b0e1d7652937d6cbdaf4018c7b6fc009a7dd6c3047351e2eddda745de43f

COPY deploy/pwa/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/admin/dist/ /usr/share/nginx/html/
