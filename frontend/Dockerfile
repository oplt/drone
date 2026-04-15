FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY=replace-me
ARG VITE_GOOGLE_MAPS_MAP_ID=replace-me
ARG VITE_CESIUM_ION_TOKEN=replace-me

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY=$VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY \
    VITE_GOOGLE_MAPS_MAP_ID=$VITE_GOOGLE_MAPS_MAP_ID \
    VITE_CESIUM_ION_TOKEN=$VITE_CESIUM_ION_TOKEN

RUN npm run build

FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
