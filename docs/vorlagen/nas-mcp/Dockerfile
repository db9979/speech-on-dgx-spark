# MCP-Dateiserver auf der NAS, gehärtet (Anleitung: docs/de/apis-und-einbinden.md, „MCP-Server auf der NAS“).
# Basis nur mit Digest: docker pull node:22-alpine
#   docker image inspect --format '{{index .RepoDigests 0}}' node:22-alpine
# und den Wert hinter @ unten eintragen. Ein Update ist ein neuer Digest und ein neuer Bau, nie „latest“.
FROM node:22-alpine@sha256:DIGEST_HIER_EINTRAGEN
WORKDIR /app
# Feste Versionen aus package-lock.json, beim Bauen statt bei jedem Start; keine Install-Skripte
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
USER node
# Liest nur /data; spricht MCP über Streamable HTTP auf Port 8000 im internen Netz (kein Port nach außen)
ENTRYPOINT ["node_modules/.bin/supergateway", "--stdio", "node_modules/.bin/mcp-server-filesystem /data", "--outputTransport", "streamableHttp", "--port", "8000"]
