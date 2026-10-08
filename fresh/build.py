"""Build public configuration, keeping notification API keys server-side."""
import hashlib
import json
import os
from urllib.parse import urlsplit
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def build(root=ROOT,env=None):
    env=os.environ if env is None else env;root=Path(root)
    password=env.get('SITE_PASSWORD','')
    if not password:raise RuntimeError('Brak sekretu SITE_PASSWORD — nie publikuję panelu bez konfiguracji dostępu.')
    config={'password_hash':hashlib.sha256(password.encode()).hexdigest(),'onesignal_app_id':env.get('ONESIGNAL_APP_ID',''),'repository':env.get('GITHUB_REPOSITORY','xlvlcl/arbi'),'public_url':env.get('APP_PUBLIC_URL','https://xlvlcl.github.io/arbi/')}
    reader=env.get('SOURCE_READER_URL','').strip();parts=urlsplit(reader)
    if parts.scheme=='https' and parts.hostname and not parts.username and not parts.password and not parts.query and not parts.fragment and parts.path in ('','/'):
        config['data_url']=reader.rstrip('/')+'/feed/latest'
    (root/'web').mkdir(parents=True,exist_ok=True)
    (root/'web/config.json').write_text(json.dumps(config),encoding='utf-8')
    print('Konfiguracja strony gotowa. Klucze usług powiadomień pozostają w sekretach.')
    return config
if __name__=='__main__':build()
