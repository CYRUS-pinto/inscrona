@echo off
REM Inscrona Mobile - Development Runner
REM Run this from the mobile/ directory

echo Starting Inscrona Mobile development server...
echo.

REM Check if node_modules exists
if not exist node_modules (
    echo Installing dependencies...
    npm install
    echo.
)

echo Starting Expo...
npx expo start --clear