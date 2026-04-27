FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . /app/

ENV NODE_ENV=development

EXPOSE 3000

CMD ["npm", "run", "dev"]
