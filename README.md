# CFDDNS (Cloudflare Dynamic DNS)

CFDDNS keeps your Cloudflare DNS records updated when your home/server IP changes.
It includes a web UI with profile management and authentication.

## What you get

- Automatic DDNS updates for Cloudflare
- Support for `A` (IPv4) and `AAAA` (IPv6)
- Multiple DNS profiles in one UI
- Manual "Run now" button
- Login-protected web UI
- Runs as a `systemd` service on Linux

## Before you install

You need:

- A Linux machine with `systemd`
- `curl` available
- A Cloudflare API token with:
	- Zone → DNS: Edit
	- Zone → Zone: Read

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/SzponerZoli/cfddns/main/scripts/install.sh | sudo bash
```


The installer:

- Detects machine architecture (`amd64`/`arm64`) (coming soon!)
- Downloads the matching binary release
- Creates service user `cfddns`
- Creates and starts `cfddns.service`
- Stores config in `/usr/share/cfddns/config.json`
- Stores runtime settings in `/etc/default/cfddns`

## First login

Open:

- `http://SERVER_IP:8080`

Default login:

- Username: `admin`
- Password: `admin`

Change username/password immediately in the web UI.

## Configure DNS in the UI

1. Create/select a profile.
2. Fill Cloudflare API token and Zone ID.
3. Set record type (`A` or `AAAA`).
4. Add record names (comma-separated).
5. Save and click "Run Update Now".

Notes:

- DNS records should already exist in Cloudflare.
- `TTL=1` means automatic TTL on Cloudflare.
- Minimum interval is 30 seconds.

## Change port

Edit:

```bash
sudo nano /etc/default/cfddns
```

Set values you want, for example:

```bash
CFDDNS_HOST=0.0.0.0
CFDDNS_PORT=9090
```

Then restart:

```bash
sudo systemctl restart cfddns
```

## Service management

```bash
sudo systemctl status cfddns
sudo systemctl restart cfddns
sudo journalctl -u cfddns -f
```

## Update to a newer release

Run the installer again:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/scripts/install.sh | sudo bash
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/scripts/uninstall.sh | sudo bash
```

Keep config by default. To remove config too:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/scripts/uninstall.sh | sudo KEEP_CONFIG=0 bash
```

## File locations

- Binary: `/opt/cfddns/cfddns`
- Service: `/etc/systemd/system/cfddns.service`
- Runtime env: `/etc/default/cfddns`
- App config/profiles: `/usr/share/cfddns/config.json`

## Troubleshooting

- Service does not start:
	- `sudo journalctl -u cfddns -n 100 --no-pager`
- UI not reachable:
	- Check port in `/etc/default/cfddns`
	- Check firewall/open port
- DNS not updating:
	- Verify Cloudflare token permissions
	- Verify Zone ID and record names
