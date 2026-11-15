FROM node:22-alpine AS ui-builder
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd -r chronos && useradd -r -g chronos chronos
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY --from=ui-builder /ui/dist ./ui/dist
RUN pip install --no-cache-dir .
USER chronos
EXPOSE 8010
ENTRYPOINT ["chronos"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8010"]
