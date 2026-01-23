#!/usr/bin/env bash
# Self-hosted GitHub Actions runner setup for macOS (Darwin arm64)
# This script sets up Docker, installs dependencies, and configures the runner

set -euo pipefail

echo "🚀 Setting up self-hosted GitHub Actions runner on macOS..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}❌ This script is for macOS only${NC}"
    exit 1
fi

# Check architecture
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo -e "${YELLOW}⚠️  This script is optimized for Apple Silicon (arm64). Intel Macs may need adjustments.${NC}"
fi

echo -e "${GREEN}✓ macOS detected (${ARCH})${NC}"

# Step 1: Install Docker
echo ""
echo "📦 Step 1: Installing Docker..."
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker already installed: $(docker --version)${NC}"
else
    echo "Choose Docker installation method:"
    echo "  1) Docker Desktop (GUI, recommended)"
    echo "  2) Colima (CLI only, lightweight)"
    read -p "Enter choice [1 or 2]: " docker_choice
    
    if [[ "$docker_choice" == "1" ]]; then
        echo "Installing Docker Desktop..."
        if command -v brew &> /dev/null; then
            brew install --cask docker
            echo -e "${YELLOW}⚠️  Please open Docker Desktop and grant permissions when prompted${NC}"
            echo "Waiting for Docker to start..."
            open -a Docker
            sleep 10
            # Wait for Docker to be ready
            for i in {1..30}; do
                if docker ps &> /dev/null; then
                    echo -e "${GREEN}✓ Docker Desktop is running${NC}"
                    break
                fi
                echo "Waiting for Docker... ($i/30)"
                sleep 2
            done
        else
            echo -e "${RED}❌ Homebrew not found. Install Homebrew first: https://brew.sh${NC}"
            exit 1
        fi
    elif [[ "$docker_choice" == "2" ]]; then
        echo "Installing Colima..."
        if command -v brew &> /dev/null; then
            brew install colima docker docker-compose
            colima start --arch aarch64 --cpu 4 --memory 6
            echo -e "${GREEN}✓ Colima started${NC}"
        else
            echo -e "${RED}❌ Homebrew not found. Install Homebrew first: https://brew.sh${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ Invalid choice${NC}"
        exit 1
    fi
    
    # Verify Docker works
    if docker ps &> /dev/null; then
        echo -e "${GREEN}✓ Docker is working${NC}"
    else
        echo -e "${RED}❌ Docker installation failed or not ready${NC}"
        exit 1
    fi
fi

# Step 2: Install CLI tools
echo ""
echo "📦 Step 2: Installing CLI tools..."
if command -v brew &> /dev/null; then
    # Check jq
    if command -v jq &> /dev/null; then
        echo -e "${GREEN}✓ jq already installed: $(jq --version)${NC}"
    else
        echo "Installing jq..."
        brew install jq
    fi
    
    # Check coreutils
    if command -v gdate &> /dev/null; then
        echo -e "${GREEN}✓ coreutils already installed${NC}"
    else
        echo "Installing coreutils..."
        brew install coreutils
    fi
else
    echo -e "${YELLOW}⚠️  Homebrew not found. Please install jq and coreutils manually${NC}"
fi

# Step 3: Setup runner directory
echo ""
echo "📦 Step 3: Setting up runner directory..."
RUNNER_DIR="$HOME/actions-runner"
if [[ -d "$RUNNER_DIR" ]]; then
    echo -e "${YELLOW}⚠️  Runner directory already exists at $RUNNER_DIR${NC}"
    read -p "Continue with existing directory? [y/N]: " continue_choice
    if [[ "$continue_choice" != "y" && "$continue_choice" != "Y" ]]; then
        echo "Exiting. Remove $RUNNER_DIR and run again to start fresh."
        exit 0
    fi
else
    mkdir -p "$RUNNER_DIR"
    echo -e "${GREEN}✓ Created runner directory: $RUNNER_DIR${NC}"
fi

cd "$RUNNER_DIR"

# Step 4: Download runner
echo ""
echo "📦 Step 4: Downloading GitHub Actions runner..."
RUNNER_VERSION="3.630.0"
RUNNER_TAR="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"

if [[ ! -f "$RUNNER_TAR" ]]; then
    echo "Downloading runner ${RUNNER_VERSION}..."
    curl -o "$RUNNER_TAR" -L "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
    echo -e "${GREEN}✓ Downloaded runner${NC}"
else
    echo -e "${GREEN}✓ Runner archive already exists${NC}"
fi

# Extract if not already extracted
if [[ ! -f "./config.sh" ]]; then
    echo "Extracting runner..."
    tar xzf "$RUNNER_TAR"
    echo -e "${GREEN}✓ Extracted runner${NC}"
else
    echo -e "${GREEN}✓ Runner already extracted${NC}"
fi

# Step 5: Get repository info
echo ""
echo "📦 Step 5: Repository configuration..."
if [[ -f "./.runner" ]]; then
    echo -e "${YELLOW}⚠️  Runner already configured${NC}"
    read -p "Reconfigure? [y/N]: " reconfigure
    if [[ "$reconfigure" != "y" && "$reconfigure" != "Y" ]]; then
        echo "Skipping configuration. Runner is ready."
        exit 0
    fi
fi

echo ""
echo "To configure the runner, you need:"
echo "  1. GitHub repository URL (e.g., https://github.com/OWNER/REPO)"
echo "  2. Runner registration token"
echo ""
echo "Get the token from:"
echo "  GitHub → Your Repo → Settings → Actions → Runners → New self-hosted runner → macOS"
echo ""
read -p "Enter repository URL (e.g., https://github.com/OWNER/REPO): " REPO_URL
read -p "Enter runner registration token: " RUNNER_TOKEN
read -p "Enter runner name [paper-runner-mac]: " RUNNER_NAME
RUNNER_NAME="${RUNNER_NAME:-paper-runner-mac}"

# Step 6: Configure runner
echo ""
echo "📦 Step 6: Configuring runner..."
./config.sh \
    --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels paper-runner,mac \
    --work _work

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}✓ Runner configured successfully${NC}"
else
    echo -e "${RED}❌ Runner configuration failed${NC}"
    exit 1
fi

# Step 7: Install as LaunchAgent
echo ""
echo "📦 Step 7: Installing as LaunchAgent (auto-start on login)..."
read -p "Install as LaunchAgent? [Y/n]: " install_service
if [[ "$install_service" != "n" && "$install_service" != "N" ]]; then
    ./svc.sh install
    ./svc.sh start
    ./svc.sh status
    echo -e "${GREEN}✓ Runner service installed and started${NC}"
    echo ""
    echo "Runner will automatically start on login."
    echo "Logs: $RUNNER_DIR/_diag/*.log"
else
    echo -e "${YELLOW}⚠️  Service not installed. Run manually with: cd $RUNNER_DIR && ./run.sh${NC}"
fi

# Step 8: Prevent sleep during runs
echo ""
echo "📦 Step 8: Sleep prevention..."
echo "To prevent sleep during workflow runs:"
echo "  1. System Settings → Battery → Options → Prevent automatic sleeping on power adapter"
echo "  2. Or run: caffeinate -dimsu &"
echo ""
read -p "Start caffeinate now? [y/N]: " start_caffeinate
if [[ "$start_caffeinate" == "y" || "$start_caffeinate" == "Y" ]]; then
    caffeinate -dimsu &
    echo -e "${GREEN}✓ Caffeinate started (prevents sleep)${NC}"
fi

# Summary
echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Verify runner is online: GitHub → Settings → Actions → Runners"
echo "  2. Update workflow files to use: runs-on: self-hosted, labels: [paper-runner]"
echo "  3. Test with: GitHub → Actions → Run workflow"
echo ""
echo "Runner commands:"
echo "  cd $RUNNER_DIR"
echo "  ./svc.sh status    # Check status"
echo "  ./svc.sh stop      # Stop service"
echo "  ./svc.sh start     # Start service"
echo "  ./svc.sh uninstall # Remove service"
echo ""
echo "Logs: $RUNNER_DIR/_diag/*.log"


