#!/usr/bin/env bash
# =============================================================================
# Trippo - Oracle Cloud Always Free (Ubuntu 24.04 ARM64) Bootstrap Script
# =============================================================================
# This script prepares a fresh Ubuntu 24.04 LTS instance on Oracle Cloud:
# 1. Updates and upgrades base system packages
# 2. Configures iptables / netfilter to allow HTTP (80) & HTTPS (443) traffic
# 3. Installs official Docker Engine and Docker Compose plugin
# 4. Configures the 'ubuntu' user for non-root Docker usage
# 5. Prepares /opt/trippo directory for deployment
# =============================================================================

set -euo pipefail

echo "==> [1/5] Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release iptables-persistent netfilter-persistent

echo "==> [2/5] Configuring firewall rules (iptables)..."
# Oracle Cloud Ubuntu images have restrictive default iptables rules blocking ports 80/443.
# We insert ACCEPT rules if they are not already present.
if ! sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    echo "    Opening port 80 (HTTP)..."
    sudo iptables -I INPUT 6 -p tcp --dport 80 -j ACCEPT
fi

if ! sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null; then
    echo "    Opening port 443 (HTTPS)..."
    sudo iptables -I INPUT 6 -p tcp --dport 443 -j ACCEPT
fi

echo "    Saving persistent firewall rules..."
sudo netfilter-persistent save

echo "==> [3/5] Installing Docker Engine & Docker Compose plugin..."
sudo install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
fi

ARCH=$(dpkg --print-architecture)
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> [4/5] Adding 'ubuntu' user to docker group..."
sudo usermod -aG docker ubuntu

echo "==> [5/5] Creating deployment folder structure at /opt/trippo..."
sudo mkdir -p /opt/trippo/data/capsules
sudo chown -R ubuntu:ubuntu /opt/trippo

echo "============================================================================="
echo " Bootstrap complete!"
echo " Log out and log back in, or run 'newgrp docker' to enable docker without sudo."
echo " Deployment directory: /opt/trippo"
echo "============================================================================="
