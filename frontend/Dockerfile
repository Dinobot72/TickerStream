# STAGE 1: Build the App
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

# Copy source code and build
COPY . .
RUN yarn build --configuration production

# STAGE 2: Run the SSR Server
FROM node:20-alpine

WORKDIR /app

# Copy the built application from the 'build' stage
# We copy the entire 'stockBot' folder which contains both 'server' and 'browser' directories
COPY --from=build /app/dist/stockBot /app/dist/stockBot

# Set environment variables
ENV PORT=4000
ENV NODE_ENV=production

# Expose the port defined in server.ts (default is 4000)
EXPOSE 4000

# Start the server
CMD ["node", "dist/stockBot/server/server.mjs"]