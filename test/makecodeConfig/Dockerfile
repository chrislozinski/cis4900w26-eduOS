FROM node:20-slim

RUN apt-get update && apt-get install -y git python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

# Install PXT CLI globally
RUN npm install -g pxt

# Clone pxt-microbit (includes pxt-core as a proper dependency tree)
RUN git clone --depth=1 https://github.com/microsoft/pxt-microbit.git /build/pxt-microbit

WORKDIR /build/pxt-microbit

# Install all dependencies (this pulls pxt-core correctly into node_modules)
RUN npm install

# Build the static package — pxtarget.json is here, pxt-core is fully intact
RUN pxt staticpkg

# Output: /build/pxt-microbit/built/packaged/