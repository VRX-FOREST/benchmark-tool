FROM node:20-slim AS builder

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# Servir les fichiers statiques avec un serveur léger
FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/out ./out

EXPOSE 3000
CMD ["serve", "out", "-l", "3000"]
