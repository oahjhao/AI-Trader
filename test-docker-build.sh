#!/bin/bash

# Test script for Docker builds
# This script tests building both Docker images locally

set -e

echo "🔧 Testing Docker builds for AI-Trader..."

# Test building trader-app image
echo "📦 Building trader-app image..."
docker build -t trader-app-test -f Dockerfile .

# Test building trader-frontend image
echo "🌐 Building trader-frontend image..."
docker build -t trader-frontend-test -f Dockerfile.frontend .

echo "✅ Both Docker images built successfully!"
echo ""
echo "📋 Built images:"
docker images | grep -E "(trader-app-test|trader-frontend-test)"
echo ""
echo "🧪 To run a quick test:"
echo "   docker run --rm trader-app-test python --version"
echo "   docker run --rm trader-frontend-test nginx -v"