# kak

A file server that supports static serving, uploading, searching, accessing control, webdav...

[![CI](https://github.com/sigoden/dufs/actions/workflows/ci.yaml/badge.svg)](https://github.com/sigoden/dufs/actions/workflows/ci.yaml)

kak is a Python implementation of [dufs](https://github.com/sigoden/dufs) - a distinctive utility file server.

## Features

- Serve static files
- Download folder as zip file
- Upload files and folders (Drag & Drop)
- Create/Edit/Search files
- Resumable/partial uploads/downloads
- Access control
- Support https
- Support webdav
- Easy to use with curl
- **HTTP Range support** (206 Partial Content, 416 Range Not Satisfiable)
- **Upload reliability** (atomic writes, file locking, SHA256 verification)
- **Security hardening** (rate limiting, brute-force protection, secure headers)
- **Request size limits** (configurable max request/upload sizes)
- **Pre-signed URLs** (time-limited secure sharing)
- **Share links** (expiration, password protection, download limits)
- **Prometheus metrics** (connections, speed, errors)
- **JSON access logs** (structured logging)
- **IP access control** (allowlist/denylist)
- **Audit logging** (security event tracking)
- **SQLite search index** (fast search for large directories)
- **Dark mode** (web UI)
- **Upload progress** (speed indicator)

## Installation

### Prerequisites

- Python 3.8+
- pip

### Install the Package

```bash
cd pythonServer
pip install .
```

This installs the `kak` command globally.

### Install in Editable Mode (for development)

```bash
cd pythonServer
pip install -e .
```

## Usage

### Quick Start

Navigate to any folder and run:

```bash
# Serve current folder on port 8080 (read-only)
kak

# Serve with ALL features enabled (upload, delete, search, archive)
kak -A

# Serve on a specific port with all features
kak -A -p 8080

# Serve a specific folder
kak --serve-path /path/to/folder
```

### Command Line Options

```bash
kak --help
```

Common Options:
- `-A, --all` - Enable all features (upload, delete, search, archive)
- `-p, --port PORT` - Port to bind to (default: 8080)
- `--serve-path PATH` - Directory to serve (default: .)
- `--hidden PATTERN` - Hidden file patterns (can repeat)
- `--cors ORIGIN` - CORS origins (can repeat)
- `--reload` - Enable auto-reload for development
- `--rate-limit N` - Rate limit: requests per minute (default: 60)
- `--burst-limit N` - Burst limit: max requests in 5 seconds (default: 10)
- `--max-request-size SIZE` - Max request size (default: 100MB)
- `--max-upload-size SIZE` - Max upload size (default: 10GB)

Size format: `100MB`, `1GB`, `10TB` etc.

### Using Configuration File

```bash
python3 __main__.py --config config.yaml
```

## Examples

Serve current working directory in read-only mode

```
kak
```

Allow all operations like upload/delete/search/create/edit...

```
kak -A
```

Only allow upload operation

```
kak --allow-upload
```

Serve a specific directory

```
kak Downloads
```

Serve a single file

```
kak linux-distro.iso
```

Serve a single-page application like react/vue

```
kak --render-spa
```

Serve a static website with index.html

```
kak --render-index
```

Require username/password

```
kak -a admin:123@/:rw
```

Listen on specific host:ip

```
kak -b 127.0.0.1 -p 80
```

Use https

```
-cert my.crtkak --tls --tls-key my.key
```

## API

Upload a file

```bash
curl -T path-to-file http://127.0.0.1:8080/new-path/path-to-file
```

Download a file

```bash
curl http://127.0.0.1:8080/path-to-file           # download the file
curl http://127.0.0.1:8080/path-to-file?hash      # retrieve the sha256 hash of the file
```

Download a folder as zip file

```bash
curl -o path-to-folder.zip http://127.0.0.1:8080/path-to-folder?zip
```

Delete a file/folder

```bash
curl -X DELETE http://127.0.0.1:8080/path-to-file-or-folder
```

Create a directory

```bash
curl -X MKCOL http://127.0.0.1:8080/path-to-folder
```

Move the file/folder to the new path

```bash
curl -X MOVE http://127.0.0.1:8080/path -H "Destination: http://127.0.0.1:8080/new-path"
```

List/search directory contents

```bash
curl http://127.0.0.1:8080?q=Dockerfile           # search for files, similar to `find -name Dockerfile`
curl http://127.0.0.1:8080?simple                 # output names only, similar to `ls -1`
curl http://127.0.0.1:8080?json                   # output paths in json format
```

With authorization (Both basic or digest auth works)

```bash
curl http://127.0.0.1:8080/file --user user:pass                 # basic auth
curl http://127.0.0.1:8080/file --user user:pass --digest        # digest auth
```

Resumable downloads

```bash
curl -C- -o file http://127.0.0.1:8080/file
```

Resumable uploads

```bash
# Get current file size for offset validation
upload_offset=$(curl -I -s http://127.0.0.1:8080/file | tr -d '\r' | sed -n 's/content-length: //p')
dd skip=$upload_offset if=file status=none ibs=1 | \
  curl -X PATCH -H "Content-Range: bytes $upload_offset-$(($upload_offset + $(stat -c %s file) - 1))/$(stat -c %s file)" \
  --data-binary @- http://127.0.0.1:8080/file
```

Upload with SHA256 verification

```bash
# Calculate hash before upload
file_hash=$(sha256sum file | cut -d' ' -f1)

# Upload with hash verification
curl -X PUT -H "X-Content-SHA256: $file_hash" --data-binary @file http://127.0.0.1:8080/file

# Request final hash in response
curl -X PUT -H "X-Verify-SHA256: true" --data-binary @file http://127.0.0.1:8080/file
# Response includes: X-Content-SHA256: <hash>
```

HTTP Range downloads (resume support)

```bash
# Download with range support (browser resumable downloads)
curl -C- -o file http://127.0.0.1:8080/file

# Download specific range
curl -r 0-1023 -o part1.bin http://127.0.0.1:8080/file

# Download last 1MB
curl -r -1048576- -o last_mb.bin http://127.0.0.1:8080/file
```

Health checks

```bash
curl http://127.0.0.1:8080/__dufs__/health
```

## Access Control

kak supports account based access control. You can control who can do what on which path with `--auth`/`-a`.

```
kak -a admin:admin@/:rw -a guest:guest@/
kak -a user:pass@/:rw,/dir1 -a @/
```

1. Use `@` to separate the account and paths. No account means anonymous user.
2. Use `:` to separate the username and password of the account.
3. Use `,` to separate paths.
4. Use path suffix `:rw`/`:ro` set permissions: `read-write`/`read-only`. `:ro` can be omitted.

- `-a admin:admin@/:rw`: `admin` has complete permissions for all paths.
- `-a guest:guest@/`: `guest` has read-only permissions for all paths.
- `-a user:pass@/:rw,/dir1`: `user` has read-write permissions for `/*`, has read-only permissions for `/dir1/*`.
- `-a @/`: All paths is publicly accessible, everyone can view/download it.

**Auth permissions are restricted by kak global permissions.** If kak does not enable upload permissions via `--allow-upload`, then the account will not have upload permissions even if it is granted `read-write`(`:rw`) permissions.

### Hide Paths

kak supports hiding paths from directory listings via option `--hidden <glob>,...`.

```
kak --hidden .git,.DS_Store,tmp
```

kak --hidden '.*'                          # hidden dotfiles
kak --hidden '*.log' --hidden '*.lock'

## Security Features

### Rate Limiting

Protect against DoS attacks with rate limiting:

```bash
kak --rate-limit 100 --burst-limit 20
```

- `--rate-limit` - Maximum requests per minute per IP (default: 60)
- `--burst-limit` - Maximum requests in 5-second window (default: 10)

### Request Size Limits

Limit upload and request sizes:

```bash
kak --max-request-size 50MB --max-upload-size 5GB
```

### Secure HTTP Headers

kak automatically adds security headers to all responses:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`
- `Permissions-Policy`
- `X-XSS-Protection`
- `Referrer-Policy`

### Brute-Force Protection

After 5 failed authentication attempts, the IP is temporarily blocked for 5 minutes.

## Phase 2 Features

### Pre-signed Temporary Download Links

Generate time-limited URLs for secure file sharing:

```bash
# Create a pre-signed URL (expires in 1 hour)
curl -X POST http://127.0.0.1:8080/__dufs__/presign \
  -H "Content-Type: application/json" \
  -d '{"path": "/secret.pdf", "expires_in": 3600}'

# Response:
# {"url": "http://localhost:8080/secret.pdf?token=abc123&share=xyz", "token": "abc123", "expires_in": 3600}

# Access the file using the pre-signed URL
curl "http://127.0.0.1:8080/secret.pdf?token=abc123&share=xyz"
```

### Share Links with Expiration

Create shareable links with expiry dates, download limits, and optional password:

```bash
# Create a share link (expires in 24 hours, max 10 downloads)
curl -X POST http://127.0.0.1:8080/__dufs__/share \
  -H "Content-Type: application/json" \
  -d '{"path": "/documents", "expires_in": 86400, "download_limit": 10}'

# Response:
# {"id": "abc123", "url": "http://localhost:8080/__dufs__/s/abc123", "path": "/documents", ...}

# Create password-protected share
curl -X POST http://127.0.0.1:8080/__dufs__/share \
  -H "Content-Type: application/json" \
  -d '{"path": "/private", "password": "mypassword"}'

# Access with password
curl "http://127.0.0.1:8080/__dufs__/s/abc123?password=mypassword"

# List all shares
curl http://127.0.0.1:8080/__dufs__/shares

# Delete a share
curl -X DELETE http://127.0.0.1:8080/__dufs__/share/abc123
```

### Prometheus Metrics

Monitor server performance:

```bash
# Get Prometheus metrics
curl http://127.0.0.1:8080/__dufs__/metrics

# Example metrics:
# kak_uptime_seconds 1234.5
# kak_requests_total{method="GET"} 100
# kak_requests_total{status="200"} 95
# kak_requests_total{status="404"} 5
# kak_bytes_downloaded_total 104857600
# kak_active_connections 2
# kak_request_duration_seconds_bucket{le="0.1"} 80
```

### JSON Access Logs

Enable JSON-formatted logs for structured logging:

```bash
kak --log-format json
```

Output example:
```json
{"timestamp": "2024-01-15T10:30:00+0000", "remote_addr": "192.168.1.1", "method": "GET", "path": "/file.txt", "status": 200, "duration_ms": 12.5}
```

### Streaming ZIP Downloads

ZIP files are now generated streaming for large folders (>100 files), avoiding memory issues:

```bash
# Download folder as ZIP
curl -o folder.zip "http://127.0.0.1:8080/myfolder?zip"

# With compression level (0-9)
curl -o folder.zip "http://127.0.0.1:8080/myfolder?zip&level=9"
```

## Phase 3: Advanced Security

### IP Access Control

Configure IP allowlists and denylists via config file:

```yaml
# config.yaml
allowlist:
  - 192.168.1.0/24
  - 10.0.0.0/8
denylist:
  - 10.0.0.5
deny_mode: deny  # "deny" = block listed, "allow" = allow only listed
```

### Audit Logging

Enable audit logging for security events:

```bash
kak --audit-log /var/log/kak/audit.log
```

### 2FA/TOTP Authentication

For users who want extra security, 2FA can be enabled (requires `pyotp` package):

```bash
pip install pyotp
```

### Fail2ban Integration

Generate Fail2ban configuration for brute-force protection:

```python
from backend.security import generate_fail2ban_jail
config = generate_fail2ban_jail()
print(config['jail'])
print(config['filter'])
```

## Phase 4: Search & Indexing

### SQLite Search Index

Enable indexed search for faster results on large directories:

```yaml
# config.yaml
enable_index: true
index_db: /var/lib/kak/index.db
background_index: true
```

### Metadata Caching

File metadata is automatically cached (TTL: 5 minutes) to reduce disk I/O.

## Phase 5: Web UI Improvements

### Dark Mode

The web UI now supports dark mode:
- Click the moon/sun icon in the header to toggle
- Your preference is saved in localStorage
- Automatically follows system preference on first visit

### Upload Progress

Uploads now show:
- Progress bar with percentage
- Upload speed (e.g., "2.5 MB/s")
- Bytes transferred (e.g., "1.2 GB / 2.5 GB")

### Context Menu Actions

Right-click on files for additional actions:
- **Copy Link** - Copy direct download link to clipboard
- **Share** - Create a temporary share link

---

## License

Copyright (c) 2022-2024 dufs-developers.

kak is made available under the terms of either the MIT License or the Apache License 2.0, at your option.

See the LICENSE-APACHE and LICENSE-MIT files for license details.

## Acknowledgments

wdezzo-kak is a Python implementation inspired by [dufs](https://github.com/sigoden/dufs), the file server originally developed by [sigoden](https://github.com/sigoden).

The architectural concepts, feature model, and design philosophy of dufs directly influenced this project.

I would like to acknowledge and thank sigoden [contributors](https://github.com/sigoden/dufs/graphs/contributors) for creating dufs, which served as the technical foundation and motivation for the development of kak.
