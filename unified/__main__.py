import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description='Run the Garden State shared research workspace.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--env-file', help='Existing reputation .env.local file; secrets stay on the server.')
    args = parser.parse_args()
    if args.env_file:
        os.environ['GARDEN_ENV_FILE'] = args.env_file
    uvicorn.run('unified.server:create_app', factory=True, host=args.host, port=args.port, workers=1)


if __name__ == '__main__':
    main()
