rooted-graphene OTA
===

See [rooted-graphene](https://github.com/schnatterer/rooted-graphene/) for more details.

This repo executes the builds for the actual OTAs.

You can find the OTA server URLs here:  
https://rooted-graphene.github.io/ota/

Local / CI usage
---

To build a single device OTA locally (defaults: `device-id=oriole`, `magisk-preinit-device=metadata`):

```bash
python3 scripts/build_oriole_publish.py
```

Signing material is read from files by default:

- `ota.key` (used to compute `KEY_OTA_BASE64`)
- `ota.crt` (used to compute `CERT_OTA_BASE64`)
- `avb.key` (used to compute `KEY_AVB_BASE64`)

Common overrides:

```bash
MAGISK_VERSION=v30.7 python3 scripts/build_oriole_publish.py
OTA_VERSION=latest python3 scripts/build_oriole_publish.py

# Optional: provide passphrases (otherwise rooted-ota.sh may prompt)
PASSPHRASE_AVB='...' PASSPHRASE_OTA='...' python3 scripts/build_oriole_publish.py
```

Docker (daily build + HTTP server)
---

Build the image:

```bash
docker build -t rooted-ota .
```

Run the container (builds immediately, then every 24 hours; serves publish/ on port 80):

```bash
docker run --rm -p 80:80 \
	-v "$PWD/keys:/app/keys" \
	-v "$PWD/publish:/app/publish" \
	rooted-ota
```
