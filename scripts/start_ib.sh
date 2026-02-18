#!/bin/bash
#
# Start IB Gateway headless with VNC access, then the trading bot.
#
# WHAT IT DOES:
#   1. Starts Xvfb (virtual display) so IB Gateway can run without a physical screen
#   2. Starts fluxbox (minimal window manager) - required by IB Gateway
#   3. Starts x11vnc - exposes the display via VNC so you can log into IB from your Mac
#   4. Starts IB Gateway
#   5. Waits for you to press ENTER after you've logged into IB (including MFA)
#   6. Starts the trading bot via Docker (ib_trading_bot containers)
#
# PREREQUISITES (on EC2):
#   - Xvfb, fluxbox, x11vnc installed (apt install xvfb fluxbox x11vnc)
#   - IB Gateway installed at /home/ubuntu/IBGateway
#   - Java 17 (apt install openjdk-17-jdk)
#   - Docker + ib_trading_bot cloned/deployed
#   - VNC password: run once: x11vnc -storepasswd /home/ubuntu/.vnc/passwd
#
# USAGE:
#   ./scripts/start_ib.sh
#   Or alias: echo 'alias ib="/home/ubuntu/ib_trading_bot/scripts/start_ib.sh"' >> ~/.bashrc && source ~/.bashrc
#   Then type: ib
#
# IB GATEWAY CONFIG:
#   In IB Gateway: Configure → API → Settings: Enable socket clients, port 4001, add 127.0.0.1 to trusted IPs.
#
set -e

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export INSTALL4J_JAVA_HOME=$JAVA_HOME
export PATH=$JAVA_HOME/bin:$PATH

IBG_DIR=/home/ubuntu/IBGateway
DISPLAY_NUM=:1
VNC_PORT=5901
VNC_PASS=/home/ubuntu/.vnc/passwd
LOG_DIR=/home/ubuntu/logs

mkdir -p $LOG_DIR
mkdir -p /home/ubuntu/.vnc

echo "Cleaning old processes..."
pkill -f Xvfb 2>/dev/null || true
pkill -f fluxbox 2>/dev/null || true
pkill -f x11vnc 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1
sleep 2

if [ ! -f "$VNC_PASS" ]; then
    echo "ERROR: VNC password not found at $VNC_PASS"
    echo "Run once: x11vnc -storepasswd /home/ubuntu/.vnc/passwd"
    exit 1
fi
chmod 600 $VNC_PASS

echo "Starting Xvfb..."
Xvfb $DISPLAY_NUM -screen 0 1920x1080x24 &
sleep 2
export DISPLAY=$DISPLAY_NUM

echo "Starting fluxbox..."
fluxbox &
sleep 2

echo "Starting x11vnc..."
x11vnc -display $DISPLAY -rfbauth $VNC_PASS -localhost -rfbport $VNC_PORT -forever -bg -o $LOG_DIR/x11vnc.log
sleep 2

echo "Starting IB Gateway..."
cd $IBG_DIR
nohup ./ibgateway > $LOG_DIR/ibgateway.log 2>&1 &
sleep 8

echo ""
echo "Connect VNC: ssh -i YOUR_KEY -L 5901:localhost:5901 ubuntu@YOUR_EC2_IP"
echo "Then open VNC Viewer → localhost:5901"
echo ""
echo "Press ENTER here once you have completed IB Gateway login..."
read

echo "Starting bot..."
cd /home/ubuntu/ib_trading_bot
docker compose -f docker-compose.yml -f docker-compose.ec2.yml up -d

echo ""
echo "SUCCESS - Bot started"
echo ""