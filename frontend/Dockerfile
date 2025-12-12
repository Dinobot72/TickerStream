FROM node:20 AS build

WORKDIR /app

# Copy package files and install dependencies
COPY package.json yarn.lock ./
RUN yarn install

# Copy source code and build
COPY . .
# Use production configuration
RUN yarn build --configuration production

# STAGE 2: Serve with Nginx
FROM nginx:alpine

# Copy the built app from the previous stage
# NOTE: Check your 'angular.json' "outputPath" if this path differs!
# Based on your package.json name, it's likely 'dist/stock-bot/browser' or 'dist/stock-bot'
COPY --from=build /app/dist/stockBot/browser /usr/share/nginx/html8

# Copy custom Nginx config (created in step 3)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]