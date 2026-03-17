# Reverse Proxy Setup

Claw Voicebox runs on port 8080. Use a reverse proxy with SSL for secure remote access.

## Option 1: Caddy (Recommended — automatic SSL)

### Install Caddy
```bash
sudo apt install caddy
# or: brew install caddy
```

### Caddyfile
```caddyfile
voice.yourdomain.com {
    reverse_proxy localhost:8080
}
```

That's it. Caddy automatically gets and renews Let's Encrypt SSL certificates.

### Start
```bash
sudo caddy start
```

## Option 2: Nginx + Let's Encrypt

### Install
```bash
sudo apt install nginx certbot python3-certbot-nginx
```

### Nginx config (`/etc/nginx/sites-available/voicebox`)
```nginx
server {
    listen 80;
    server_name voice.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

### Enable + SSL
```bash
sudo ln -s /etc/nginx/sites-available/voicebox /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d voice.yourdomain.com
```

## Option 3: Traefik (Docker-native)

Add to your `docker-compose.yml`:

```yaml
services:
  claw-voicebox:
    # ... existing config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.voicebox.rule=Host(`voice.yourdomain.com`)"
      - "traefik.http.routers.voicebox.tls.certresolver=letsencrypt"
      - "traefik.http.services.voicebox.loadbalancer.server.port=8080"
    networks:
      - traefik

networks:
  traefik:
    external: true
```

## Firewall

Make sure port 443 (HTTPS) and 80 (HTTP for cert renewal) are open:

```bash
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp
```
