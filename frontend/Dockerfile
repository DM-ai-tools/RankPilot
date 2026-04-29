# RankPilot SPA — build context must be the repository root.
# In Railway: set this file as the Dockerfile path for the *frontend* service
# (Service → Settings → Build → Dockerfile path = `frontend/Dockerfile`).
# Do not rely on the root Dockerfile for the frontend; that image is API-only.
FROM node:22-alpine AS build
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM node:22-alpine
WORKDIR /app
RUN npm install -g serve@14.2.4
COPY --from=build /build/dist ./dist
EXPOSE 3000
CMD ["sh", "-c", "exec serve -s dist -l ${PORT:-3000}"]
