# Deploying to AWS

## Option A — EC2 (this is the one you're using)

One-time host setup, then Docker Compose runs the app, with Nginx in front
for a real domain/HTTPS and systemd so it survives reboots.

1. **Launch the instance**: Amazon Linux 2023 or Ubuntu 22.04/24.04,
   t3.small is plenty to start. Security group: allow inbound 22 (SSH,
   your IP only), 80 and 443 (HTTP/HTTPS, from anywhere) — do **not**
   expose 8080 publicly, only Nginx should be reachable from the internet.
2. **Push this repo to GitHub first** (from your machine):
   ```bash
   cd rozzgaar-chatbot
   git init && git add . && git commit -m "initial commit"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
   (`.env` is gitignored — confirm it's not in `git status` before pushing.)
3. **SSH into the instance** and run the setup script:
   ```bash
   curl -O https://raw.githubusercontent.com/<you>/<repo>/main/deploy/ec2-setup.sh
   chmod +x ec2-setup.sh
   ./ec2-setup.sh https://github.com/<you>/<repo>.git
   ```
   This installs Docker + Compose and clones the repo to
   `~/rozzgaar-chatbot`.
4. **Fill in real secrets**:
   ```bash
   cd ~/rozzgaar-chatbot
   nano .env   # was seeded from .env.example - fill in the real values
   ```
5. **Start it**:
   ```bash
   sudo docker compose up -d --build
   curl http://localhost:8080/          # should return {"status":"ok",...}
   ```
6. **(Recommended) Put Nginx in front** so port 8080 isn't exposed and you
   get a real domain/HTTPS:
   ```bash
   sudo dnf install -y nginx || sudo apt-get install -y nginx   # AL2023 / Ubuntu
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/rozzgaar-chatbot   # Ubuntu
   # AL2023: cp into /etc/nginx/conf.d/rozzgaar-chatbot.conf instead, and
   # skip the sites-enabled symlink step - it uses conf.d directly.
   sudo ln -s /etc/nginx/sites-available/rozzgaar-chatbot /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl enable --now nginx
   # then HTTPS: sudo certbot --nginx -d yourdomain.example.com
   ```
   Edit `server_name` in `deploy/nginx.conf` to your real domain first.
7. **(Recommended) Auto-start on reboot**:
   ```bash
   sudo cp deploy/rozzgaar-chatbot.service /etc/systemd/system/
   # edit WorkingDirectory in that file if your username isn't ec2-user
   sudo systemctl daemon-reload
   sudo systemctl enable --now rozzgaar-chatbot
   ```
8. Set `PUBLIC_BACKEND_URL` in `.env` to your final URL (the domain if you
   set up Nginx, otherwise `http://<ec2-public-ip>:8080`), and
   `ALLOWED_ORIGINS` to your actual frontend domain — then
   `sudo docker compose up -d --build` again to pick up the change.
9. **Build the knowledge base once**:
   ```bash
   curl -X POST http://localhost:8080/ingest/refresh \
     -H "X-Admin-Secret: <your real ADMIN_SECRET>"
   ```
   Re-run this whenever course content changes (a cron entry calling that
   same curl command works well). `data/kb.joblib` is mounted as a volume
   in `docker-compose.yml`, so it survives `docker compose up --build`.

**Redeploying after a code change**: `git pull && sudo docker compose up -d --build`
on the instance. Or wire up GitHub Actions to SSH in and run that same
command on push — ask if you want that workflow file too.

## Option B — AWS App Runner, no Docker (uses `apprunner.yaml`)

Simplest path: push this repo to GitHub, point App Runner at it, done.

1. `git init && git add . && git commit -m "initial commit"` then push to a
   new GitHub repo. (`.env` is gitignored — confirm it's NOT in `git status`.)
2. AWS Console → **App Runner** → **Create service** → source: **Source
   code repository** → connect your GitHub account → pick the repo/branch.
3. Deployment settings: it will auto-detect `apprunner.yaml` — use
   "Automatic" deployment trigger if you want push-to-deploy.
4. Under **Configure service → Environment variables**, add every key from
   `.env.example` with your real values (use "Environment secrets" pointing
   at AWS Secrets Manager for `GROQ_API_KEY`, `ROZZGAAR_OPEN_KEY`, and
   `ADMIN_SECRET` specifically).
5. Set `PUBLIC_BACKEND_URL` to the App Runner URL App Runner gives you
   after first deploy (you'll need to redeploy once you know it), and
   `ALLOWED_ORIGINS` to your actual frontend domain(s) — not `*`.
6. Deploy. Health check hits `/` (already returns 200 with a JSON status).
7. Once live, call the ingest endpoint once to build the knowledge base:
   ```bash
   curl -X POST https://<your-app-runner-url>/ingest/refresh \
     -H "X-Admin-Secret: <your real ADMIN_SECRET>"
   ```
   Re-run this whenever course content changes (cron/EventBridge on a
   schedule works well since `data/kb.joblib` isn't committed to git).

## Option C — Docker → ECR → App Runner / ECS Fargate

Use this if you want a portable image (also works for ECS, Lightsail
containers, or App Runner from an image instead of source).

```bash
# Build
docker build -t rozzgaar-chatbot .

# Test locally with real env values
docker run --rm -p 8080:8080 --env-file .env rozzgaar-chatbot

# Push to ECR
aws ecr create-repository --repository-name rozzgaar-chatbot
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker tag rozzgaar-chatbot:latest <account-id>.dkr.ecr.<region>.amazonaws.com/rozzgaar-chatbot:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/rozzgaar-chatbot:latest
```

Then in App Runner: **Create service** → source: **Container registry** →
point at that ECR image → same environment variables as Option A → deploy.
(For ECS Fargate instead: create a task definition referencing this image,
set the same env vars/secrets, expose port 8080 behind an ALB.)

## Notes that apply either way

- **Rotate `GROQ_API_KEY` and `ROZZGAAR_OPEN_KEY`** before going live —
  the ones in your local `.env` were shared outside this project and
  should be treated as burned. Get a fresh Groq key at
  console.groq.com/keys.
- Never set `ALLOWED_ORIGINS=*` in production — lock it to your real
  frontend domain(s).
- `data/kb.joblib` is intentionally not committed (see `.gitignore`) — the
  app builds it at runtime via `/ingest/refresh`. If you'd rather ship it
  pre-built, remove it from `.gitignore`/`.dockerignore` and add a
  `COPY data ./data` line in the Dockerfile.
- `static/embed.js`'s backend URL is auto-rewritten from
  `PUBLIC_BACKEND_URL` by `app/main.py` — just set that env var, don't
  hand-edit the JS.
