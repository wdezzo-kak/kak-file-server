# kak

A file server that supports static serving, uploading, searching, accessing control, webdav...

[![CI](https://github.com/sigoden/dufs/actions/workflows/ci.yaml/badge.svg)](https://github.com/sigoden/dufs/actions/workflows/ci.yaml)

kak is a Python implementation of [dufs](https://github.com/sigoden/dufs) - a distinctive utility file server.

<img width="1315" height="625" alt="Screenshot from 2026-02-24 02-05-49" src="https://github.com/user-attachments/assets/6a939a8e-3e89-4a6d-866d-0ba63dff34b9" />

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
upload_offset=$(curl -I -s http://127.0.0.1:8080/file | tr -d '\r' | sed -n 's/content-length: //p')
dd skip=$upload_offset if=file status=none ibs=1 | \
  curl -X PATCH -H "X-Update-Range: append" --data-binary @- http://127.0.0.1:8080/file
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

## License

Copyright (c) 2022-2024 dufs-developers.

kak is made available under the terms of either the MIT License or the Apache License 2.0, at your option.

See the LICENSE-APACHE and LICENSE-MIT files for license details.

## Acknowledgments

This project is a Python port of [dufs](https://github.com/sigoden/dufs) by [sigoden](https://github.com/sigoden).

Thank you to sigoden and all the [contributors](https://github.com/sigoden/dufs/graphs/contributors) for creating such an amazing file server!

Original dufs is licensed under MIT or Apache-2.0.
