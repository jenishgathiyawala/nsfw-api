# Security

## Reporting a problem

Please **don't open a public issue** for a security problem. Report it privately:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe what you found, how to reproduce it and what an attacker could do.

You will get a reply as soon as possible. Please give time for a fix before you share the details.

Never attach real NSFW or personal photos to a report. A generated test image or a
description is enough.

## Supported versions

Only the latest version on the `main` branch gets security fixes.

## What is in scope

- Bypassing the API key
- Crashing or hanging the server with a crafted file (image parsing, decompression bombs,
  oversized requests)
- Reading files or running code on the server
- Leaking uploaded images or other data

A photo that is classified wrongly is an accuracy problem, not a security problem. Open a
normal issue for it, but don't attach the photo.

## Running it safely

- Always set `API_KEYS` on a public server, and keep the key in your backend only.
- Put it behind HTTPS (for example Caddy, see [docs/deploy-oracle.md](docs/deploy-oracle.md)).
- Keep the default size limits (`MAX_UPLOAD_MB`, `MAX_PIXELS`) unless you need larger ones.
