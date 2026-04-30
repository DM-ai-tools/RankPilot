# SPA — build context MUST be the `frontend/` folder (not repo root).
#
# Railway (recommended): Service → Settings → Source → Root Directory = `frontend`
#   → Build → Dockerfile path = `Dockerfile` (this file).
# That way this service never sees `backend/` or the root API Dockerfile, so you
# will not get SQLAlchemy/Python logs on the “front-end” deploy.

FROM node:22-alpine AS build
WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM node:22-alpine
WORKDIR /app
RUN npm install -g serve@14.2.4
COPY --from=build /build/dist ./dist
EXPOSE 3000
CMD ["sh", "-c", "exec serve -s dist -l ${PORT:-3000}"]
