# kak - File Server Guide

A modern, full-featured file server written in Python using FastAPI, inspired by [dufs](https://github.com/sigoden/dufs).

## Features

- **File Operations**: Upload, download, delete, rename, move files
- **Directory Listing**: HTML, JSON, and plain text formats
- **Large File Support**: Range requests and streaming
- **ZIP Archives**: Download directories as ZIP files
- **WebDAV Support**: PROPFIND, MKCOL, COPY, MOVE, LOCK, UNLOCK
- **Authentication**: Basic, Digest, and Token authentication
- **Access Control**: Path-based permissions
- **Modern UI**: Beautiful file manager interface

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

### Install in Editable Mode (for development)

```bash
cd pythonServer
pip install -e .
```

Then you can edit the code and see changes immediately.

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

Full Options:
- `--host HOST` - Host to bind to (default: 0.0.0.0)
- `--config CONFIG` - Configuration file path

### Using Configuration File

```bash
python3 __main__.py --config config.yaml
```

Example `config.yaml`:

```yaml
host: 0.0.0.0
port: 8080
serve_path: /path/to/serve
prefix: ""

auth:
  allow_anonymous: true
  users:
    - username: admin
      password: secret
      access: read_write

hidden:
  - ".*"
  - "*.log"

allow_upload: true
allow_delete: true
allow_search: true
allow_archive: true

log_format: '$remote_addr "$request" $status'
```

## API Endpoints

### File Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List directory (HTML) |
| GET | `/path` | Download file or list directory |
| GET | `/?json` | List as JSON |
| GET | `/?simple` | List as plain text |
| GET | `/?q=term` | Search files |
| GET | `/?zip` | Download as ZIP |
| GET | `/?hash` | Get file SHA256 hash |
| PUT | `/path` | Upload/create file |
| PATCH | `/path` | Resumable upload |
| DELETE | `/path` | Delete file/directory |
| MKCOL | `/path` | Create directory |
| COPY | `/path` | Copy file (WebDAV) |
| MOVE | `/path` | Move/rename (WebDAV) |
| PROPFIND | `/path` | List properties (WebDAV) |
| LOCK | `/path` | Lock file (WebDAV) |
| UNLOCK | `/path` | Unlock file (WebDAV) |

### Special Endpoints

| Endpoint | Description |
|----------|-------------|
| `/__kak__/health` | Health check |
| `/__ui__/` | Modern file manager UI |
| `/files/` | File manager UI (alternative) |

## Web Interface

Open `http://localhost:8080/__ui__/` in your browser.

### Features

- **Grid/List View**: Toggle between grid and list views
- **Drag & Drop**: Upload files by dragging them
- **Context Menu**: Right-click for actions (open, download, rename, delete)
- **Multi-Select**: Checkbox to select multiple files
- **Search**: Search files by name
- **Breadcrumb**: Navigate through directories
- **Dark Mode**: Automatic dark mode support

## Authentication

### Basic Authentication

```bash
curl -u username:password http://localhost:8080/
```

### Token Authentication

Generate a token (requires authentication):

```bash
# Get token from response headers or body
curl http://localhost:8080/?tokengen -u username:password
```

Use token:

```bash
curl http://localhost:8080/?token=your_token_here
```

### Access Control

Configure in `config.yaml`:

```yaml
access:
  - path: /
    perm: read_write    # read_write, read_only, index_only
  - path: /public
    perm: read_only
  - path: /private
    perm: index_only    # can only list, cannot read
```

## Examples

### Download a File

```bash
curl -O http://localhost:8080/path/to/file.txt
```

### Upload a File

```bash
curl -T file.txt http://localhost:8080/path/to/file.txt
```

### Create a Directory

```bash
curl -X MKCOL http://localhost:8080/new-folder/
```

### Delete a File

```bash
curl -X DELETE http://localhost:8080/path/to/file.txt
```

### Download Directory as ZIP

```bash
curl -o folder.zip http://localhost:8080/folder/?zip
```

### Search Files

```bash
curl "http://localhost:8080/?q=document"
```

## Common Examples

```bash
# Serve current folder with all features (upload, delete, search, archive)
kak -A

# Serve on port 9000 with all features
kak -A -p 9000

# Serve with CORS enabled
kak -A --cors "*"

# Hide certain files
kak -A --hidden ".*" --hidden "*.log"

# Read-only (default)
kak

# Read-only on custom port
kak -p 3000
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `host` | string | "0.0.0.0" | Bind host |
| `port` | int | 8080 | Bind port |
| `serve_path` | string | "." | Directory to serve |
| `single_file` | string | null | Serve single file |
| `prefix` | string | "" | URL prefix |
| `allow_upload` | bool | true | Allow file uploads |
| `allow_delete` | bool | true | Allow deletion |
| `allow_search` | bool | true | Allow search |
| `allow_archive` | bool | true | Allow ZIP download |
| `render_index` | bool | false | Render index.html |
| `render_try_index` | bool | false | Try index.html |
| `render_spa` | bool | false | SPA mode |
| `enable_webdav` | bool | true | Enable WebDAV |
| `cors` | list | [] | CORS origins |
| `hidden` | list | [] | Hidden file patterns |

## Development

Run with auto-reload:

```bash
python3 __main__.py --reload
```

## Production

For production, use a proper ASGI server:

```bash
# Install uvicorn with standard features
pip install uvicorn[standard]

# Run with SSL
uvicorn backend.server:app --host 0.0.0.0 --port 443 --ssl-certfile=cert.pem --ssl-keyfile=key.pem
```

Or use Gunicorn:

```bash
gunicorn backend.server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
```

## License

MIT
