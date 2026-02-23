import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.server import run_server
from backend.config import config


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='kak - A file server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
    parser.add_argument('--config', '-c', help='Configuration file path')
    parser.add_argument('--serve-path', default='.', help='Path to serve')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload')
    
    args = parser.parse_args()
    
    if args.config:
        config.load_from_file(args.config)
    
    config.host = args.host
    config.port = args.port
    
    if args.serve_path:
        config.serve_path = args.serve_path
    
    run_server(config.host, config.port, args.reload)


if __name__ == '__main__':
    main()
