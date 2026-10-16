# The web image: the production build, served by nginx, which also proxies
# /api to the API service (nginx/default.conf.template). The final image has
# no Node runtime and no npm packages, only the built files.

FROM node:20.20.2-slim AS build
WORKDIR /app
# Exactly the versions in package-lock.json; `npm ci` fails if the lockfile and
# package.json disagree instead of resolving a new set.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Build time only: Vite writes this into the bundle as the API base the
# browser uses. The default is the same-origin path nginx proxies.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM nginx:1.30.5-alpine
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
# Run time only: where nginx sends /api (host:port on the compose network).
ENV REGDELTA_API_UPSTREAM=api:8000
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
