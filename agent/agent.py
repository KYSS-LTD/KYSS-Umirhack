import argparse
import base64
import json
import os
import platform
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import nacl.encoding
import nacl.signing

CONFIG_DIR = Path.home() / '.agent'
PRIVATE_KEY_PATH = CONFIG_DIR / 'private.key'
PUBLIC_KEY_PATH = CONFIG_DIR / 'public.key'
CONFIG_PATH = CONFIG_DIR / 'config.json'
DEFAULT_INTERVAL = 5


def ensure_keys() -> tuple[str, str]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return PRIVATE_KEY_PATH.read_text(), PUBLIC_KEY_PATH.read_text()

    signing_key = nacl.signing.SigningKey.generate()
    verify_key = signing_key.verify_key
    private_b64 = signing_key.encode(encoder=nacl.encoding.Base64Encoder).decode()
    public_b64 = verify_key.encode(encoder=nacl.encoding.Base64Encoder).decode()
    PRIVATE_KEY_PATH.write_text(private_b64)
    PUBLIC_KEY_PATH.write_text(public_b64)
    os.chmod(PRIVATE_KEY_PATH, 0o600)
    return private_b64, public_b64


def sign_payload(private_key_b64: str, payload: dict, timestamp: int) -> str:
    key = nacl.signing.SigningKey(private_key_b64, encoder=nacl.encoding.Base64Encoder)
    msg = json.dumps(payload, sort_keys=True, separators=(',', ':')) + f'*{timestamp}'
    sig = key.sign(msg.encode()).signature
    return base64.b64encode(sig).decode()


def get_local_ips() -> list[str]:
    ips = set()
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if ':' not in addr:
                ips.add(addr)
    except Exception:
        pass
    return sorted(list(ips))


def run_task(task: dict, allowed_commands: set[str], timeout_sec: int = 20) -> tuple[str, str, str]:
    task_type = task.get('task_type')
    try:
        if task_type == 'check_cpu':
            out = subprocess.check_output(['uptime'], text=True, timeout=5)
            return 'done', out[:4000], out[:4000]
        if task_type == 'check_ram':
            out = subprocess.check_output(['free', '-m'], text=True, timeout=5)
            return 'done', out[:4000], out[:4000]
        if task_type == 'check_disk':
            out = subprocess.check_output(['df', '-h'], text=True, timeout=5)
            return 'done', out[:4000], out[:4000]
        if task_type == 'check_ports':
            ports = [22, 80, 443]
            states = []
            for p in ports:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                code = s.connect_ex(('127.0.0.1', p))
                states.append(f'{p}:{"open" if code == 0 else "closed"}')
                s.close()
            result = ', '.join(states)
            return 'done', result, result
        if task_type == 'check_system_info':
            result = {
                'hostname': platform.node(),
                'ip_addresses': get_local_ips(),
                'os_version': platform.platform(),
                'network_interfaces': get_local_ips(),
                'connectivity': 'ok' if socket.gethostbyname('localhost') else 'failed',
            }
            text = json.dumps(result, ensure_ascii=False)
            return 'done', text[:4000], text[:4000]
        if task_type == 'run_command':
            cmd = task.get('command', '')
            if cmd not in allowed_commands:
                return 'failed', 'команда отклонена whitelist', 'команда отклонена whitelist'
            args = cmd.split(' ')
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec, check=False)
            output = (result.stdout + '\n' + result.stderr)[:4000]
            return ('done' if result.returncode == 0 else 'failed', output, output)
        return 'failed', 'неизвестный тип задачи', 'неизвестный тип задачи'
    except Exception as exc:
        msg = f'ошибка выполнения: {exc}'
        return 'failed', msg[:4000], msg[:4000]


def register(base_url: str, token: str, agent_uid: str | None = None):
    private_key, public_key = ensure_keys()
    agent_uid = agent_uid or str(uuid.uuid4())
    payload = {
        'agent_uid': agent_uid,
        'hostname': platform.node() or 'unknown',
        'public_key': public_key,
        'registration_token': token,
    }
    with httpx.Client(timeout=10, verify=True) as client:
        r = client.post(f'{base_url}/api/agents/register', json=payload)
        r.raise_for_status()
        data = r.json()
    cfg = {'base_url': base_url, 'agent_uid': data['agent_id'], 'public_key': public_key, 'agent_token': data['agent_token']}
    CONFIG_PATH.write_text(json.dumps(cfg))
    return private_key, cfg


def load_or_register(base_url: str, token: str):
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text())
        private_key, _ = ensure_keys()
        return private_key, cfg
    return register(base_url, token)


def loop(base_url: str, agent_uid: str, agent_token: str, private_key: str, public_key: str, interval: int):
    allowed = {c.strip() for c in os.getenv('ALLOWED_COMMANDS', 'uptime,df -h,free -m').split(',') if c.strip()}
    headers = {'Authorization': f'Bearer {agent_token}'}
    while True:
        now = int(time.time())
        hb_payload = {
            'hostname': platform.node(),
            'public_key': public_key,
            'ip_addresses': get_local_ips(),
            'os_version': platform.platform(),
            'network_interfaces': get_local_ips(),
        }
        envelope = {
            'agent_uid': agent_uid,
            'timestamp': now,
            'nonce': str(uuid.uuid4()),
            'payload': hb_payload,
            'signature': sign_payload(private_key, hb_payload, now),
        }
        try:
            with httpx.Client(timeout=10, verify=True, headers=headers) as client:
                client.post(f'{base_url}/api/agents/heartbeat', json=envelope).raise_for_status()
                task_resp = client.post(f'{base_url}/api/agents/tasks/next', json=envelope)
                task_resp.raise_for_status()
                task = task_resp.json().get('task')
                if task:
                    status, result, logs = run_task(task, allowed_commands=allowed)
                    task_payload = {'task_uid': task['task_uid'], 'status': status, 'result': result, 'logs': logs}
                    now2 = int(time.time())
                    result_env = {
                        'agent_uid': agent_uid,
                        'timestamp': now2,
                        'nonce': str(uuid.uuid4()),
                        'payload': task_payload,
                        'signature': sign_payload(private_key, task_payload, now2),
                    }
                    client.post(f'{base_url}/api/tasks/result', json=result_env).raise_for_status()
        except Exception:
            pass
        time.sleep(max(5, min(interval, 10)))


def main():
    parser = argparse.ArgumentParser(description='KYSSCHECK Agent')
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--registration-token', required=True)
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL)
    args = parser.parse_args()

    private, cfg = load_or_register(args.base_url, args.registration_token)
    public = PUBLIC_KEY_PATH.read_text()
    loop(args.base_url, cfg['agent_uid'], cfg['agent_token'], private, public, args.interval)


if __name__ == '__main__':
    main()
