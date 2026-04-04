#!/usr/bin/env python3
import socket
import sys
import time


def wait_for(host: str, port: int, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f'[wait] {host}:{port} is available')
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f'Timeout waiting for {host}:{port}')


def main() -> int:
    targets = sys.argv[1:]
    if not targets:
        targets = ['postgres:5432', 'redis:6379']
    for target in targets:
        host, port = target.split(':', 1)
        wait_for(host, int(port))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
