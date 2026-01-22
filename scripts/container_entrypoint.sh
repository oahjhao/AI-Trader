#!/bin/bash
# AI-Trader Container Entrypoint Script
# This script starts the MCP services in the background and then runs the trader runner.

set -e

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "📦 Loading environment variables from .env file..."
    # Export variables from .env, ignoring comments and empty lines
    set -a
    source .env
    set +a
    echo "✅ Environment variables loaded from .env file"
else
    echo "⚠️  .env file not found, using existing environment variables"
fi

# Extract signature from command line arguments
# Typically the command is: configs/xxx.json --signature YOUR_SIGNATURE
for i in "$@"; do
    if [[ "$prev_arg" == "--signature" ]]; then
        export SIGNATURE="$i"
        echo "📝 Set SIGNATURE=$SIGNATURE for MCP services"
        # Pre-create log directory to ensure MCP services can write logs
        mkdir -p "logs/$SIGNATURE"
        echo "📁 Created log directory: logs/$SIGNATURE"
        break
    fi
    prev_arg="$i"
done

# Define cleanup function
cleanup() {
    echo "🛑 Shutting down MCP services..."
    # Kill all python processes except the current one
    # This is a bit aggressive but works in a single-purpose container
    pkill -f "python.*tool_.*py" || true
    pkill -f "python.*start_mcp_services.py" || true
    echo "✅ Cleanup complete"
}

# Set trap for cleanup
trap cleanup EXIT

# 1. Start MCP services in background
echo "🚀 Starting MCP services in background..."
python agent_tools/start_mcp_services.py &

# 2. Wait for MCP services to be ready
# We check if the ports are listening
echo "⏳ Waiting for MCP services to initialize..."
MAX_RETRIES=60
RETRY_COUNT=0
# Default math port 8000 as a health check
while ! (exec 3<>/dev/tcp/localhost/8000) 2>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "❌ MCP services failed to start within timeout"
        echo "📋 Checking if MCP service processes are running..."
        ps aux | grep -E "tool_(math|search|trade|get_price)" | grep -v grep || echo "No MCP processes found"
        exit 1
    fi
    sleep 2
done
echo "✅ MCP services are up and running"

# 3. Execute the requested command (usually the runner)
echo "🤖 Executing trader runner with arguments: $@"
python -m trader.runner "$@"

echo "🎉 Agent execution finished"
