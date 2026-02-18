#!/bin/bash
set -e

# Run this script on the EC2 instance (ssh in, then ./scripts/deploy.sh)
# EC2 must have: git, docker, and GitHub SSH access for git clone
# Uses /home/ubuntu/ib_trading_bot — does NOT touch trading-system (existing prod)

echo "Starting deployment..."

DEPLOY_DIR=/home/ubuntu/ib_trading_bot
rm -rf "$DEPLOY_DIR"
git clone git@github.com:abaitas/ib_trading_bot.git "$DEPLOY_DIR"
rm -rf "$DEPLOY_DIR/.github"

cd "$DEPLOY_DIR"
docker compose -f docker-compose.yml -f docker-compose.ec2.yml down || true
docker compose -f docker-compose.yml -f docker-compose.ec2.yml up -d --build --force-recreate

echo "Deployment complete."

