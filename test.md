# kak File Server - Comprehensive Testing Guide

This document provides comprehensive tests for all features of the kak file server.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Server Setup](#server-setup)
3. [CLI Tests](#cli-tests)
4. [Browser Tests](#browser-tests)
5. [Test Summary Checklist](#test-summary-checklist)

---

## Prerequisites

```bash
# Install dependencies
pip install -e .

# Create test directory
mkdir -p /tmp/kak-test
cd /tmp/kak-test

# Create test files
echo "Hello World" > test.txt
dd if=/dev/urandom of=large-file.bin bs=1M count=10 2>/dev/null
mkdir -p test-folder
echo "file1" > test-folder/file1.txt
echo "file2" > test-folder/file2.txt

# Start server
kak -A -p 8080 &
sleep 2
```

---

## Server Setup

```bash
# Test health endpoint
curl -s http://localhost:8080/__dufs__/health
# Expected: {"status":"ok","version":"0.3.0"}
```

---

## CLI Tests

### 1. Basic File Operations

```bash
# Download file
curl -s http://localhost:8080/test.txt
# Expected: Hello World

# Get file hash
curl -s http://localhost:8080/test.txt?hash
# Expected: SHA256 hash

# List directory (JSON)
curl -s "http://localhost:8080/?json" | python3 -m json.tool

# List directory (simple)
curl -s "http://localhost:8080/?simple"

# Search files
curl -s "http://localhost:8080/?q=txt"

# Create directory
curl -X MKCOL http://localhost:8080/new-folder
# Expected: 201 Created

# Delete file
curl -X DELETE http://localhost:8080/test.txt
# Expected: 204 No Content
```

### 2. HTTP Range Tests

```bash
# Test 206 Partial Content
curl -s -H "Range: bytes=0-9" http://localhost:8080/test.txt
# Expected: Hello Wor

# Test suffix range (last 5 bytes)
curl -s -H "Range: bytes=-5" http://localhost:8080/test.txt
# Expected: orld

# Test open-ended range
curl -s -H "Range: bytes=6-" http://localhost:8080/test.txt
# Expected: World

# Test 416 Range Not Satisfiable
curl -sI -H "Range: bytes=1000-" http://localhost:8080/test.txt | head -1
# Expected: HTTP/1.1 416 Range Not Satisfiable

# Check Accept-Ranges header
curl -sI http://localhost:8080/test.txt | grep Accept-Ranges
# Expected: Accept-Ranges: bytes

# Resume download
curl -C- -o resumed.txt http://localhost:8080/large-file.bin
```

### 3. Upload Tests

```bash
# Simple PUT upload
curl -X PUT -T test.txt http://localhost:8080/uploaded.txt
# Expected: 201 Created

# Upload with SHA256 verification
SHA256=$(sha256sum test.txt | cut -d' ' -f1)
curl -X PUT -H "X-Content-SHA256: $SHA256" -T test.txt http://localhost:8080/verified.txt
# Expected: 201 Created (or 422 if hash mismatch)

# Request hash in response
curl -sI -X PUT -H "X-Verify-SHA256: true" -T test.txt http://localhost:8080/verify-response.txt | grep X-Content-SHA256
```

### 4. Resumable Upload Tests

```bash
# Get current file size
SIZE=$(stat -c%s test.txt)
echo "File size: $SIZE bytes"

# Upload first half
head -c $((SIZE/2)) test.txt > partial.txt
curl -X PUT -T partial.txt http://localhost:8080/resume-test.txt

# Get current size
curl -sI http://localhost:8080/resume-test.txt | grep -i content-length

# Append second half
OFFSET=$(curl -sI http://localhost:8080/resume-test.txt | grep -i content-length | awk '{print $2}')
tail -c +$((OFFSET+1)) test.txt > partial2.txt
curl -X PATCH -H "Content-Range: bytes $OFFSET-$((SIZE-1))/$SIZE" -T partial2.txt http://localhost:8080/resume-test.txt
# Expected: 204 No Content
```

### 5. Authentication Tests

```bash
# Start with auth
kak -A -p 8081 -a admin:password@/:rw &
sleep 2

# Without auth (should fail)
curl -s -X PUT --data "test" http://localhost:8081/protected.txt
# Expected: 403 Forbidden

# With valid auth
curl -s -X PUT --data "test" -u admin:password http://localhost:8081/protected.txt
# Expected: 201 Created

# Generate token
curl -s "http://localhost:8081/?tokengen" -u admin:password
# Expected: {"token": "..."}

# Use token
curl -s "http://localhost:8081/test.txt?token=YOUR_TOKEN"
```

### 6. Rate Limiting Tests

```bash
# Make many requests quickly
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/test.txt
done
# Expected: Most 200, some 429
```

### 7. Share Links Tests

```bash
# Create share link
curl -s -X POST http://localhost:8080/__dufs__/share \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{"path": "/test.txt", "expires_in": 3600}'
# Expected: {"id": "...", "url": "http://...", ...}

# Create password-protected share
curl -s -X POST http://localhost:8080/__dufs__/share \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{"path": "/test.txt", "password": "secret123"}'

# Access share
curl -s "http://localhost:8080/__dufs__/s/SHARE_ID?password=secret123"

# List shares
curl -s http://localhost:8080/__dufs__/shares -u admin:password

# Delete share
curl -s -X DELETE http://localhost:8080/__dufs__/share/SHARE_ID -u admin:password
```

### 8. Pre-signed URL Tests

```bash
# Generate pre-signed URL
curl -s -X POST http://localhost:8080/__dufs__/presign \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{"path": "/test.txt", "expires_in": 3600}'
# Expected: {"url": "...", "token": "...", ...}

# Access with token
curl -s "http://localhost:8080/test.txt?token=TOKEN&share=ID"
```

### 9. Prometheus Metrics Tests

```bash
# Get metrics
curl -s http://localhost:8080/__dufs__/metrics
# Expected: Prometheus format metrics

# Check specific metrics
curl -s http://localhost:8080/__dufs__/metrics | grep -E "^kak_"
```

### 10. ZIP Download Tests

```bash
# Download folder as ZIP
curl -s "http://localhost:8080/test-folder?zip" -o test.zip
unzip -l test.zip

# With compression level
curl -s "http://localhost:8080/test-folder?zip&level=9" -o compressed.zip
```

### 11. WebDAV Tests

```bash
# PROPFIND
curl -s -X PROPFIND http://localhost:8080/ -H "Depth: 1"

# MOVE
curl -s -X MOVE http://localhost:8080/test.txt \
  -H "Destination: http://localhost:8080/moved.txt"

# LOCK
curl -s -X LOCK http://localhost:8080/test.txt \
  -H "Timeout: Infinite" \
  -H "Content-Type: application/xml" \
  -d "<lockowner><owner>test</owner></lockowner>"

# UNLOCK
curl -s -X UNLOCK http://localhost:8080/test.txt -H "Lock-Token: <token>"
```

### 12. Edge Cases

```bash
# Path traversal (should be blocked)
curl -s "http://localhost:8080/../etc/passwd"
# Expected: 404 Not Found

# Invalid range
curl -sI -H "Range: bytes=abc" http://localhost:8080/test.txt

# Non-existent file
curl -s http://localhost:8080/nonexistent.txt
# Expected: 404 Not Found
```

---

## Browser Tests

### 1. Web UI Access

```
URL: http://localhost:8080/
Expected: File Manager UI loads
```

### 2. Dark Mode

```javascript
// In browser console:
// Click the moon/sun icon in header
// Check if dark-mode class is added to body

document.body.classList.contains('dark-mode')
// Expected: true (when dark mode is on)

// Check localStorage
localStorage.getItem('kak-theme')
// Expected: 'dark' or 'light'
```

### 3. File Upload with Progress

```javascript
// In browser:
// 1. Click Upload button
// 2. Select a large file (>10MB)
// 3. Observe:
//    - Progress bar fills up
//    - Speed shows (e.g., "2.5 MB/s")
//    - Percentage shows (e.g., "45%")
//    - Bytes transferred shows (e.g., "1.2 GB / 2.5 GB")
```

### 4. Context Menu - Copy Link

```javascript
// In browser:
// 1. Right-click on any file
// 2. Click "Copy Link"
// 3. Check notification appears
// 4. Verify link is in clipboard

navigator.clipboard.readText().then(text => console.log(text))
// Expected: Full URL to file
```

### 5. Context Menu - Share

```javascript
// In browser:
// 1. Right-click on any file
// 2. Click "Share"
// 3. Notification should show "Share link copied"
// 4. Check clipboard for share URL
```

### 6. View Toggle

```javascript
// In browser:
// Click the grid/list icon in header
// Expected: View toggles between grid and list

// Check list view header appears
document.querySelector('.list-view-header')
// Should be visible in list view
```

### 7. Search

```javascript
// In browser:
// Type in search box
// Expected: Files filter in real-time
// Use Cmd+K or Ctrl+K for quick search
```

### 8. Navigation

```javascript
// In browser:
// Click on folder
// Expected: Navigate into folder, URL updates

// Click back button
// Expected: Go back to previous folder
```

### 9. Mobile Responsive

```javascript
// In browser devtools:
// Toggle device toolbar (Ctrl+Shift+M)
// Select mobile device (iPhone, Android)
// Expected: UI adapts to mobile:
//   - Hamburger menu appears
//   - Sidebar becomes overlay
//   - Touch-friendly buttons
```

### 10. Drag and Drop Upload

```javascript
// In browser:
// Drag files from desktop to upload dropzone
// Expected:
//   - Dropzone highlights
//   - Files start uploading
//   - Progress shows for each file
```

### 11. Multiple File Selection

```javascript
// In browser:
// Hold Ctrl/Cmd and click multiple files
// Expected:
//   - Files get selected (checkbox)
//   - Selection count shows
//   - Action toolbar appears (download, delete, move)
```

### 12. Sorting

```javascript
// In browser:
// Click sort button in header
// Select "Name", "Size", or "Modified"
// Expected: Files reorder accordingly
```

### 13. File Preview (for images)

```javascript
// In browser:
// Click on an image file
// Expected: Image displays in viewer or new tab
```

### 14. Keyboard Shortcuts

```javascript
// In browser:
// Press Delete key with file selected
// Expected: Confirmation dialog, then delete

// Press F2 with file selected
// Expected: Rename input appears
```

### 15. Check Security Headers

```javascript
// In browser devtools Network tab:
// Click on any request
// Check Response Headers:
// Expected headers present:
//   - X-Content-Type-Options: nosniff
//   - X-Frame-Options: DENY
//   - Content-Security-Policy: ...
//   - Referrer-Policy: ...
```

---

## Test Summary Checklist

### CLI Tests

| # | Test | Status |
|---|------|--------|
| 1 | Health check | [ ] |
| 2 | Download file | [ ] |
| 3 | Get file hash | [ ] |
| 4 | List directory (JSON) | [ ] |
| 5 | List directory (simple) | [ ] |
| 6 | Search files | [ ] |
| 7 | Create directory | [ ] |
| 8 | Delete file | [ ] |
| 9 | HTTP Range 206 | [ ] |
| 10 | HTTP Range suffix | [ ] |
| 11 | HTTP Range 416 | [ ] |
| 12 | Accept-Ranges header | [ ] |
| 13 | Resume download | [ ] |
| 14 | PUT upload | [ ] |
| 15 | Upload with SHA256 | [ ] |
| 16 | Resumable upload | [ ] |
| 17 | Basic auth | [ ] |
| 18 | Token auth | [ ] |
| 19 | Rate limiting | [ ] |
| 20 | Create share link | [ ] |
| 21 | Password share | [ ] |
| 22 | Access share | [ ] |
| 23 | List shares | [ ] |
| 24 | Delete share | [ ] |
| 25 | Pre-signed URL | [ ] |
| 26 | Prometheus metrics | [ ] |
| 27 | ZIP download | [ ] |
| 28 | ZIP compression | [ ] |
| 29 | WebDAV PROPFIND | [ ] |
| 30 | WebDAV MOVE | [ ] |
| 31 | Path traversal blocked | [ ] |

### Browser Tests

| # | Test | Status |
|---|------|--------|
| 1 | Web UI loads | [ ] |
| 2 | Dark mode toggle | [ ] |
| 3 | Dark mode persistence | [ ] |
| 4 | Upload progress bar | [ ] |
| 5 | Upload speed display | [ ] |
| 6 | Copy link | [ ] |
| 7 | Share action | [ ] |
| 8 | View toggle | [ ] |
| 9 | Search | [ ] |
| 10 | Navigation | [ ] |
| 11 | Mobile responsive | [ ] |
| 12 | Drag & drop | [ ] |
| 13 | Multiple selection | [ ] |
| 14 | Sorting | [ ] |
| 15 | Security headers | [ ] |

---

## Cleanup

```bash
# Stop servers
pkill -f "kak"

# Clean test files
rm -rf /tmp/kak-test
```

---

End of Test Guide
