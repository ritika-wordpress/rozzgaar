#!/usr/bin/env bash
# Run ONCE on a fresh EC2 instance (Amazon Linux 2023 or Ubuntu 22.04/24.04)
# to install Docker + Compose and pull this repo down.
#
# Usage (as ec2-user/ubuntu, with sudo):
#   curl -O https://raw.githubusercontent.com/<you>/<repo>/main/deploy/ec2-setup.sh
#   chmod +x ec2-setup.sh
#   ./ec2-setup.sh https://github.com/<you>/<repo>.git

set -euo pipefail

REPO_URL="${1:?Usage: ./ec2-setup.sh <git-repo-url>}"
APP_DIR="$HOME/rozzgaar-chatbot"

echo "== Installing Docker =="
if command -v dnf >/dev/null 2>&1; then
  # Amazon Linux 2023
  sudo dnf update -y
  sudo dnf install -y docker git
  sudo systemctl enable --now docker
elif command -v apt-get >/dev/null 2>&1; then
  # Ubuntu
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-plugin git
  sudo systemctl enable --now docker
else
  echo "Unsupported distro - install Docker manually." >&2
  exit 1
fi

sudo usermod -aG docker "$USER" || true

echo "== Installing docker compose plugin (if missing) =="
if ! docker compose version >/dev/null 2>&1; then
  DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"
  mkdir -p "$DOCKER_CONFIG/cli-plugins"
  curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
    -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
  chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"
fi

echo "== Cloning repo =="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "!! Edit $APP_DIR/.env now and fill in real values"
  echo "   (GROQ_API_KEY, ROZZGAAR_OPEN_KEY, ADMIN_SECRET, ALLOWED_ORIGINS,"
  echo "    PUBLIC_BACKEND_URL) before starting the app."
fi

echo ""
echo "Setup done. Next steps:"
echo "  1. nano $APP_DIR/.env          # fill in real secrets"
echo "  2. cd $APP_DIR && sudo docker compose up -d --build"
echo "  3. (optional) install the systemd unit: deploy/rozzgaar-chatbot.service"
echo "     so it restarts automatically on reboot."
echo ""
echo "If 'docker' commands need sudo right now, log out and back in once"
echo "(the usermod -aG docker change needs a fresh session)."
