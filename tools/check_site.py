"""Low-cost static checks for the self-contained project page and oral media."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT=Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
        self.media=[]
        self.references=[]
    def handle_starttag(self,tag,attributes):
        attributes=dict(attributes)
        if 'id' in attributes:self.ids.append(attributes['id'])
        for key in ('src','href','poster'):
            if key in attributes:self.references.append(attributes[key])
        if 'data-robustness-video' in attributes:self.media.append(attributes)
        if tag=='img':assert attributes.get('alt'), 'Image lacks alternative text'


def main():
    html=(ROOT/'index.html').read_text()
    page=Page();page.feed(html);page.close()
    assert len(page.ids)==len(set(page.ids)), 'Duplicate HTML IDs'
    assert {'temporal-coupling','robustness'}<=set(page.ids)
    assert len(page.media)==2
    for video in page.media:
        assert {'controls','autoplay','muted','loop','playsinline'}<=video.keys()
        assert video['preload']=='metadata'
    for reference in page.references:
        parsed=urlparse(reference)
        if parsed.scheme or parsed.netloc or not parsed.path:continue
        target=(ROOT/unquote(parsed.path)).resolve()
        assert target.is_relative_to(ROOT) and target.is_file(), f'Missing local asset: {reference}'
    assert 'not live yet' not in html and 'soon' not in html
    manifest=json.loads((ROOT/'assets/presentation_media.json').read_text())
    assert len(manifest['diagrams'])==2 and len(manifest['videos'])==2
    for entry in manifest['diagrams']+manifest['videos']:
        path=ROOT/entry['file']
        assert path.stat().st_size==entry['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
    for video in manifest['videos']:
        assert video['bytes']<5_000_000
        assert (video['frames'],video['fps'],video['duration'])==(240,30.,8.)
        assert (video['width'],video['height'],video['codec'],video['pixel_format'])==(1600,900,'h264','yuv420p')
    print('PASS: local links, image alternatives, unique IDs, video controls, publication links,')
    print('      media SHA256, two 8-second/30fps videos, and strict 5MB size limits.')
    for video in manifest['videos']:print(f'      {video["file"]}: {video["bytes"]:,} bytes')


if __name__=='__main__':main()
