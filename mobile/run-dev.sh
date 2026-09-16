#!/bin/bash
# Inscrona Mobile - Development Runner
# Run this from the mobile/ directory

echo "Starting Inscrona Mobile development server..."
echo

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
    echo
fi

echo "Starting Expo..."
npx expo start --clear