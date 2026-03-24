FROM node:20-slim

RUN apt-get update && apt-get install -y git python3 make g++ cmake \
    && rm -rf /var/lib/apt/lists/*

# Install PXT CLI globally
RUN npm install -g pxt

# This is the ONLY public source of sim.js — pxt-arcade-sim repo is permanently private
WORKDIR /tmp/npm-fetch
RUN npm init -y
RUN npm install pxt-arcade

# Clone pxt-arcade 
RUN git clone --depth=1 https://github.com/microsoft/pxt-arcade.git /build/pxt-arcade
WORKDIR /build/pxt-arcade

# use npm install for all dependencies, pulling pxt-core and pxt-arcade-sim pre-built from registry
RUN npm install

# This provides built/sim.js, common-sim.js, editor.js etc.
# that staticpkg needs to generate simulator.html
RUN cp -rf /tmp/npm-fetch/node_modules/pxt-arcade/built/. ./built/

# Build staticpkg now which has simulator.html, binary.js, and everything else
RUN mkdir -p public
RUN pxt staticpkg --route /

# COPY the two files that staticpkg cannot generate :
#   simulator.html : the iframe that index.html loads at "simUrl": "/simulator.html"
#   sim.css        : styles for the game canvas and controller UI
COPY simulator.html ./built/packaged/simulator.html
COPY sim.css        ./built/packaged/sim.css

# Output: /build/pxt-arcade/built/packaged/