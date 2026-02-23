import click
import os
from pathlib import Path

from .config import config


@click.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=8080, help='Port to bind to')
@click.option('--config', '-c', 'config_file', help='Configuration file path')
@click.option('--serve-path', default='.', help='Path to serve files from')
@click.option('--single-file', help='Serve a single file')
@click.option('--prefix', default='', help='URL prefix')
@click.option('--auth', help='Auth configuration file')
@click.option('--allow-anonymous', is_flag=True, default=True, help='Allow anonymous access')
@click.option('--hidden', multiple=True, help='Hidden file patterns')
@click.option('--allow-upload/--no-upload', default=True, help='Allow file uploads')
@click.option('--allow-delete/--no-delete', default=True, help='Allow file deletion')
@click.option('--allow-search/--no-search', default=True, help='Allow file search')
@click.option('--allow-archive/--no-archive', default=True, help='Allow archive downloads')
@click.option('--render-index', is_flag=True, help='Render index.html for directories')
@click.option('--render-try-index', is_flag=True, help='Try index.html, fallback to listing')
@click.option('--render-spa', is_flag=True, help='Render SPA')
@click.option('--enable-webdav/--no-webdav', default=True, help='Enable WebDAV')
@click.option('--cors', multiple=True, help='CORS origins')
@click.option('--log-format', default='$remote_addr "$request" $status', help='Log format')
@click.option('--log-file', help='Log file path')
@click.option('--tls-cert', help='TLS certificate file')
@click.option('--tls-key', help='TLS key file')
@click.option('--token-secret', help='Secret for token generation')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
def main(host, port, config_file, serve_path, single_file, prefix, auth, 
         allow_anonymous, hidden, allow_upload, allow_delete, allow_search,
         allow_archive, render_index, render_try_index, render_spa, enable_webdav,
         cors, log_format, log_file, tls_cert, tls_key, token_secret, reload):
    if config_file and os.path.exists(config_file):
        config.load_from_file(config_file)
    else:
        config.host = host
        config.port = port
        config.serve_path = serve_path
        config.prefix = prefix
        config.allow_anonymous = allow_anonymous
        config.hidden = list(hidden) if hidden else []
        config.allow_upload = allow_upload
        config.allow_delete = allow_delete
        config.allow_search = allow_search
        config.allow_archive = allow_archive
        config.render_index = render_index
        config.render_try_index = render_try_index
        config.render_spa = render_spa
        config.enable_webdav = enable_webdav
        config.cors = list(cors) if cors else []
        config.log_format = log_format
        config.log_file = log_file
        config.tls_cert = tls_cert
        config.tls_key = tls_key
        config.token_secret = token_secret
        
        if single_file:
            config.single_file = Path(single_file)
    
    from .server import run_server
    run_server(config.host, config.port, reload)


if __name__ == '__main__':
    main()
