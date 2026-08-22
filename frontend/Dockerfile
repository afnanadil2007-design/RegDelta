# Multi-stage build for the RegDelta web app.
# Builder produces the static bundle; runtime serves it with Vite preview.
FROM node:20-slim AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
FROM node:20-slim AS runtime

WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./package.json
# `vite preview` serves the built bundle; the API is reached via the compose
# network. For a single-user local tool this is sufficient (no nginx needed).
RUN npm install -g vite@5
EXPOSE 5173
CMD ["vite", "preview", "--host", "--port", "5173"]
