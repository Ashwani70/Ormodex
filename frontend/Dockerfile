# Ormodex ERP — frontend (CRA/craco build), production image.
#
# Multi-stage: build the static bundle with Node, serve it with Nginx. Railway
# terminates TLS at its edge (see docs/PRODUCTION_DEPLOYMENT_GUIDE.md), so this
# Nginx only needs to serve static files with correct caching + gzip/brotli +
# SPA fallback routing — it does not need its own cert.

FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# REACT_APP_* vars must be present at BUILD time (CRA inlines them into the
# bundle) — Railway build-time variables, not runtime ones, must supply these.
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}
ENV CI=false

RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build /usr/share/nginx/html

RUN apk add --no-cache curl

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
