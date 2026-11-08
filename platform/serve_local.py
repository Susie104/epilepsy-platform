"""Windows-compatible local research server. python serve_local.py"""
import json
import os

from waitress import serve
import server


if __name__ == '__main__':
    info = server.bootstrap()
    if not server.predictor:
        raise SystemExit('Model integrity check failed; see model/SHA256SUMS')
    if server.CONFIG['channel2_envelope']:
        from gateway.crypto import KeyStore
        store = KeyStore(server.STORE['keys'])
        if not all(store.exists(k) for k in ('model', 'platform_sign')):
            raise SystemExit('CHANNEL2 requires locally generated test/hospital keys')
    port = int(os.environ.get('PORT', '3000'))
    server.app.config['PORT'] = port
    print(json.dumps({'url': f'http://127.0.0.1:{port}', 'model_integrity': info['integrity'],
                      'channel2': server.CONFIG['channel2_envelope'], 'mode': 'local-research-demo'}), flush=True)
    serve(server.app, host='127.0.0.1', port=port, threads=8)
