"""Local preview; production hosts should mount create_app behind their web server."""
import argparse
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

from .config import Settings
from .web import create_app


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass  # URLs/headers and credentials never belong in preview logs.


def main():
    parser = argparse.ArgumentParser(description='Preview the shared NJ startup reputation module.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.host not in ('127.0.0.1', 'localhost'):
        parser.error('The development server binds locally only. Mount create_app behind HTTPS for deployment.')
    app = create_app(settings)
    with make_server(args.host, args.port, app, server_class=ThreadedServer, handler_class=QuietHandler) as server:
        print(f'NJ startup reputation preview: http://{args.host}:{args.port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            app.service.close()


if __name__ == '__main__':
    main()
