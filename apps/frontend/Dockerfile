# syntax=docker/dockerfile:1

# ---------- base ----------
FROM node:22-alpine AS base
WORKDIR /app

# ---------- dev: hot reload, source mounted by compose ----------
FROM base AS dev
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---------- build ----------
FROM base AS build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- prod: standalone output ----------
FROM base AS prod
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
