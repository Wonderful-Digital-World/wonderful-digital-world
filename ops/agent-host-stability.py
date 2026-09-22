"""Install the logged-in Mac agent host's sleep assertion and context budgets.

Run with the Hermes Python environment (PyYAML). Existing profile settings and
session databases are preserved. Gateways must be restarted separately when idle.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
import yaml


def main():
    home = Path.home()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = home / 'Library/Application Support/WDWRuntimeState/backups' / ('agent-stability-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    for resident in ('coach', 'bridget', 'mini-me'):
        profile = home / ('.hermes-' + resident)
        path = profile / 'config.yaml'
        shutil.copy2(path, backup / (resident + '-config.yaml'))
        settings = yaml.safe_load(path.read_text())
        settings.setdefault('compression', {}).update(enabled=True, threshold_tokens=32000)
        with tempfile.NamedTemporaryFile(mode='w', dir=profile, delete=False) as handle:
            yaml.safe_dump(settings, handle, sort_keys=False)
            temp = Path(handle.name)
        temp.replace(path)
    label = 'com.wdw.agent-host-awake'
    path = home / 'Library/LaunchAgents' / (label + '.plist')
    data = {'Label': label, 'ProgramArguments': ['/usr/bin/caffeinate', '-is'],
            'RunAtLoad': True, 'KeepAlive': True, 'ProcessType': 'Background'}
    if path.exists():
        shutil.copy2(path, backup / path.name)
        if plistlib.loads(path.read_bytes()) != data:
            raise RuntimeError('Existing keep-awake service has different settings; inspect before replacing')
    else:
        path.write_bytes(plistlib.dumps(data)); path.chmod(0o600)
    domain = 'gui/' + str(os.getuid())
    exists = subprocess.run(['launchctl', 'print', domain + '/' + label], capture_output=True).returncode == 0
    if not exists:
        subprocess.run(['launchctl', 'bootstrap', domain, str(path)], check=True)
    print(json.dumps({'backup': str(backup), 'compression_threshold_tokens': 32000,
                      'keep_awake_service': label, 'gateway_restart_required': True}))


if __name__ == '__main__':
    main()
