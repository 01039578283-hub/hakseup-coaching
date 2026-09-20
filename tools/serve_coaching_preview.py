"""Local static preview with explicit WebP/AVIF MIME on Windows."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.webp':'image/webp','.avif':'image/avif',
                      '.css':'text/css','.js':'application/javascript'}
    def log_message(self, *_): pass

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('--port',type=int,default=8832)
    port=args.parse_args().port
    ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,directory=str(Path(__file__).resolve().parents[1]))).serve_forever()
