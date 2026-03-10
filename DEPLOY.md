# 🚀 Guida al Deploy — Bollette Risparmio

## Il database sopravvive agli aggiornamenti?

**Sì, sempre** — il file `db.sqlite` è fuori dall'immagine Docker.  
Il volume `./data:/app/data` mappa la cartella `data/` del tuo server
dentro il container. Ricostruire o sostituire l'immagine non tocca mai
quel file.

```
server/
  bollette-risparmio/
    data/
      db.sqlite          ← MAI toccato da Docker
    docker-compose.yml
    .env
```

---

## Workflow aggiornamento versione (zero downtime)

Ogni volta che vuoi deployare una nuova versione:

```bash
# 1. Entra nella cartella del progetto sul server
cd /srv/bollette-risparmio

# 2. Scarica il nuovo zip e sostituisci il codice
unzip -o bollettaai-site-v3.zip -d .

# 3. Ricostruisci l'immagine (solo il codice cambia, data/ è intatta)
docker compose build --no-cache

# 4. Riavvia il container (2–5 secondi di downtime)
docker compose up -d --force-recreate

# 5. Verifica che sia vivo
docker compose ps
curl http://localhost:8000/api/health
```

Il file `data/db.sqlite` non viene mai toccato perché è fuori dall'immagine.

---

## Primo deploy su un server VPS

### Prerequisiti
- Ubuntu 22.04 / 24.04
- Docker + Docker Compose installati
- Porta 80/443 aperta (o usa Nginx come reverse proxy)

```bash
# Installa Docker (se non presente)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Crea la struttura
mkdir -p /srv/bollette-risparmio/data
cd /srv/bollette-risparmio

# Copia il progetto (da locale via scp)
scp bollettaai-site-v3.zip user@tuo-server:/srv/bollette-risparmio/
unzip bollettaai-site-v3.zip

# Crea il file .env
cp .env.example .env
nano .env   # inserisci le variabili d'ambiente

# Avvia
docker compose up -d

# Controlla i log
docker compose logs -f
```

---

## File .env — variabili necessarie

```env
# OBBLIGATORIO
GEMINI_API_KEY=AIza...

# Sicurezza admin panel
ADMIN_TOKEN=scegli-una-password-sicura

# Email (Resend — gratuito fino a 3000/mese)
RESEND_API_KEY=re_...
FROM_EMAIL=Bollette Risparmio <info@bolletterisparmio.it>
ADMIN_EMAIL=la-tua-email@gmail.com

# URL del sito (per link nelle email)
SITE_URL=https://www.bolletterisparmio.it

# CORS (lascia * per Render, specifica dominio in produzione)
ALLOWED_ORIGINS=https://www.bolletterisparmio.it
```

---

## Backup del database

Il DB è un singolo file — il backup è semplicissimo:

```bash
# Backup manuale
cp /srv/bollette-risparmio/data/db.sqlite \
   /srv/backup/db_$(date +%Y%m%d_%H%M%S).sqlite

# Backup automatico giornaliero (aggiungi a crontab)
# crontab -e
0 3 * * * cp /srv/bollette-risparmio/data/db.sqlite \
             /srv/backup/db_$(date +\%Y\%m\%d).sqlite \
             && find /srv/backup -name "db_*.sqlite" -mtime +30 -delete
```

---

## Nginx come reverse proxy (dominio + HTTPS)

```nginx
# /etc/nginx/sites-available/bolletterisparmio
server {
    listen 80;
    server_name www.bolletterisparmio.it bolletterisparmio.it;
    return 301 https://www.bolletterisparmio.it$request_uri;
}

server {
    listen 443 ssl;
    server_name www.bolletterisparmio.it;

    ssl_certificate     /etc/letsencrypt/live/www.bolletterisparmio.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.bolletterisparmio.it/privkey.pem;

    client_max_body_size 15M;   # per upload bollette PDF

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;   # analisi AI può richiedere ~30s
    }
}
```

```bash
# Abilita il sito e ottieni il certificato HTTPS
sudo ln -s /etc/nginx/sites-available/bolletterisparmio /etc/nginx/sites-enabled/
sudo certbot --nginx -d www.bolletterisparmio.it
sudo nginx -t && sudo systemctl reload nginx
```

---

## Render.com (attuale hosting)

Su Render il DB **non sopravvive** ai re-deploy perché il filesystem è
effimero. Hai due opzioni:

### Opzione A — Render Disk (consigliata, $1/mese)
Nel dashboard Render:
1. Vai su **Environment → Disks**
2. Aggiungi un disco: Mount Path `/app/data`, Size 1 GB
3. Il DB persiste tra i deploy

### Opzione B — Migrate su VPS
Per un'applicazione in produzione con dati reali, un VPS (Hetzner CX22
~4€/mese) è più affidabile e conveniente di Render.

---

## Comandi utili Docker

```bash
# Vedere i log in tempo reale
docker compose logs -f

# Entrare nel container (per debug)
docker exec -it bollettaai bash

# Ispezionare il DB dall'interno
docker exec -it bollettaai python3 -c "
import sqlite3
c = sqlite3.connect('/app/data/db.sqlite')
print('Bollette:', c.execute('SELECT COUNT(*) FROM bollette').fetchone()[0])
print('Offerte luce:', c.execute('SELECT COUNT(*) FROM offerte_luce').fetchone()[0])
print('Leads:', c.execute('SELECT COUNT(*) FROM leads').fetchone()[0])
"

# Riavvio veloce senza rebuild (solo config/env cambiati)
docker compose restart

# Stop completo
docker compose down

# Stop e rimozione volumi (⚠️ CANCELLA IL DB)
docker compose down -v   # ← NON eseguire in produzione
```
