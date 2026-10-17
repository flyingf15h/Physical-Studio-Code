# Viewer: built React app + Node server for Gemini tokens and design exports. Build context: repo root.
FROM node:22-slim AS build
WORKDIR /app/viewer
COPY viewer/package.json viewer/package-lock.json ./
RUN npm ci
COPY viewer/ ./
RUN npm run build

FROM node:22-slim
WORKDIR /app/viewer
ENV NODE_ENV=production PORT=8080 OUT_DIR=/data/out
COPY viewer/package.json viewer/package-lock.json ./
RUN npm ci --omit=dev
COPY --from=build /app/viewer/dist ./dist
COPY viewer/server.mjs ./
COPY viewer/server ./server
EXPOSE 8080
USER node
CMD ["node", "server.mjs"]
