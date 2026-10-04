"""Reproducible sample acquisition; never run by the application at startup."""
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]/'audio'/'samples'
REPO='nbrosowsky/tonejs-instruments'
SOURCE_COMMIT='622c2f1c32c8cfce4158ddc3eb26e518ddef37e5'

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'Gemba-Studio-build'}),timeout=60) as response:
        return response.read()

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    sha=SOURCE_COMMIT
    tree=json.loads(fetch(f'https://api.github.com/repos/{REPO}/git/trees/{sha}?recursive=1'))['tree']
    names=['guitar-acoustic','guitar-nylon','guitar-electric','piano','harp','organ']
    chosen=[]
    semis={'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
    for entry in tree:
        parts=entry['path'].split('/')
        if len(parts)!=3 or parts[0]!='samples' or parts[1] not in names or not parts[2].endswith('.mp3'): continue
        match=re.fullmatch(r'([A-G])(s?)(\d)\.mp3',parts[2])
        if not match: continue
        pitch=12*(int(match[3])+1)+semis[match[1]]+bool(match[2])
        # Upstream nylon D5 recording measures D#5; preserve its true pitch mapping.
        if parts[1]=='guitar-nylon' and pitch==74: pitch=75
        if not 35<=pitch<=96: continue
        if parts[1]=='piano' and pitch%3: continue
        chosen.append((entry['path'],parts[1],pitch))
    def save(item):
        source,bank,pitch=item
        raw=fetch(f'https://raw.githubusercontent.com/{REPO}/{sha}/{source}')
        audio,sr=sf.read(io.BytesIO(raw),always_2d=True,dtype='float32')
        # Keep recorded stereo where available. Trim only leading digital silence.
        level=np.max(np.abs(audio),axis=1)
        voiced=np.flatnonzero(level>max(.0003,float(level.max())*.003))
        if len(voiced): audio=audio[max(0,int(voiced[0])-round(sr*.002)):]
        path=ROOT/bank/f'{pitch}.flac'; path.parent.mkdir(parents=True,exist_ok=True)
        sf.write(path,audio,sr,format='FLAC',subtype='PCM_16')
        return dict(bank=bank,midi=pitch,source=source,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),rate=sr,frames=len(audio))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records=list(pool.map(save,chosen))
    (ROOT/'manifest.json').write_text(json.dumps(dict(repository=f'https://github.com/{REPO}',commit=sha,
        license='CC BY 3.0',changes='MP3 decoded to PCM16 FLAC; leading digital silence trimmed.',samples=records),indent=2),encoding='utf-8')
    for remote,local in [('LICENSE.md','UPSTREAM-LICENSE.md'),('sample-source-info.txt','SOURCE-CREDITS.txt')]:
        (ROOT/local).write_bytes(fetch(f'https://raw.githubusercontent.com/{REPO}/{sha}/{remote}'))
    print(f'Bundled {len(records)} recorded samples from {sha}')

if __name__=='__main__': main()
