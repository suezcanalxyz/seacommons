# Cloudflare Pages + Oracle Free Deploy

This is the cheapest practical live-demo setup for SeaCommons:

- Frontend on Cloudflare Pages
- Backend API on Oracle Cloud Always Free
- Public frontend domain like `demo.suezcanal.xyz`
- Public API domain like `api-demo.suezcanal.xyz`

## 1. Frontend: Cloudflare Pages

SeaCommons can now be built either for a subpath or for a root domain.

Use these build settings in Cloudflare Pages:

```text
Framework preset: None
Build command: npm ci && npm run build
Build output directory: dist
Root directory: /
```

Environment variables for the frontend:

```text
VITE_API_BASE=https://api-demo.suezcanal.xyz
VITE_PUBLIC_BASE=/
VITE_MAPTILER_KEY=your_maptiler_key
VITE_WINDY_KEY=
VITE_OWM_KEY=
```

Notes:

- `VITE_PUBLIC_BASE=/` is the correct value when Pages serves the app from the root of `demo.suezcanal.xyz`.
- If you host under a path instead, use `VITE_PUBLIC_BASE=/seacommons/`.
- The `public/_redirects` file ensures SPA fallback to `index.html`.

## 2. Backend: Oracle Cloud Always Free

Provision a small Ubuntu VM in Oracle Cloud Always Free.

Recommended shape for a demo:

- Ampere A1
- 2 OCPU
- 8 GB RAM

Open these ports in the Oracle security list / NSG:

- `22` SSH
- `80` HTTP
- `443` HTTPS
- `8000` only if you expose Uvicorn directly without Nginx

## 3. Backend install

SSH into the VM and run:

```bash
sudo apt update
sudo apt install -y git python3.12 python3.12-venv nginx
git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
python3.12 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r apps/api/requirements-api.txt
cp .env.example .env
```

Edit `.env` for demo mode:

```text
DATABASE_URL=sqlite:///./core/data/suezcanal_demo.db
REDIS_URL=redis://localhost:6379/0
MOCK=true
DEMO_PUBLIC_MODE=true
SUEZCANAL_AUTH=false
AISSTREAM_KEY=
CMEMS_USERNAME=
CMEMS_PASSWORD=
SUEZCANAL_SIGNING_KEY=change-me
```

For the cheapest demo, leave Redis unused and keep `DEMO_PUBLIC_MODE=true`.

## 4. Run the API

Quick manual test:

```bash
. .venv/bin/activate
cd apps/api
uvicorn core.api.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected demo response shape:

```json
{"status":"ok","mock":true,"demo_public_mode":true}
```

## 5. Systemd service

Create `/etc/systemd/system/seacommons-api.service`:

```ini
[Unit]
Description=SeaCommons API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/seacommons/apps/api
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/seacommons/.venv/bin/uvicorn core.api.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now seacommons-api
sudo systemctl status seacommons-api
```

## 6. Nginx reverse proxy

Create `/etc/nginx/sites-available/seacommons-api`:

```nginx
server {
    server_name api-demo.suezcanal.xyz;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then:

```bash
sudo ln -s /etc/nginx/sites-available/seacommons-api /etc/nginx/sites-enabled/seacommons-api
sudo nginx -t
sudo systemctl reload nginx
```

## 7. TLS

Use Certbot once DNS is pointed:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api-demo.suezcanal.xyz
```

## 8. DNS

Set:

- `demo.suezcanal.xyz` -> Cloudflare Pages custom domain
- `api-demo.suezcanal.xyz` -> Oracle VM public IP

## 9. Recommended rollout order

1. Bring up Oracle VM and API first.
2. Verify `https://api-demo.suezcanal.xyz/health`.
3. Deploy frontend to Cloudflare Pages with `VITE_API_BASE` set.
4. Attach `demo.suezcanal.xyz`.
5. Test `POST /api/v1/alert` from the live frontend.

## 10. Limits of the free demo

- `MOCK=true` means live SAR cases use the Gaussian fallback in hosted demo mode.
- No full production persistence guarantees with SQLite.
- No background sensors in public demo mode.
- Good for client walkthroughs, not for operations.
