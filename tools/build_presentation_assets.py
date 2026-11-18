"""Low-memory, single-threaded export of the author's oral-presentation media.

Optional rebuild (not required for GitHub Pages):
  nice -n 19 python tools/build_presentation_assets.py --pptx /path/to/final.pptx
Dependencies: Pillow, numpy, OpenCV, PyAV. No GPU or inference is used.
"""
import argparse
from contextlib import ExitStack
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from zipfile import ZipFile

import av
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CAP = 5_000_000
SPECS = (
    dict(name='noisy_guidance_comparison',slide=12,
         title='Spline refiners remain stable with noisy guidance',
         groups=('Clean guidance: sigma / L = 0','Gaussian noise: sigma / L = 0.005'),
         media=('media7.mp4','media8.mp4','media9.mp4','media10.mp4')),
    dict(name='missing_keypoints_comparison',slide=13,
         title='Spline refiners tolerate missing keypoints',
         groups=('No masking: 0 joints','Random masking: 2 joints per frame'),
         media=('media7.mp4','media8.mp4','media11.mp4','media12.mp4')),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def font(size,bold=False):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'
                              + ('-Bold' if bold else '') + '.ttf',size)


def centered(draw,xy,text,typeface,color=(35,35,35)):
    draw.text(xy,text,font=typeface,fill=color,anchor='mt')


def background(spec):
    image = Image.new('RGB',(1920,1080),'white')
    draw = ImageDraw.Draw(image)
    centered(draw,(960,16),spec['title'],font(36,True))
    for center,label in zip((478,1442),spec['groups']):
        centered(draw,(center,76),label,font(30,True))
    slots=[]
    for start in (38,1002):
        for x,w,label in ((start,461,'2D guidance'),(start+477,403,'Four-method refinement')):
            centered(draw,(x+w/2,121),label,font(23))
            slots.append(tuple(round(value*5/6) for value in (x,160,w,820)))
    draw.line((960,76,960,982),fill=(220,220,220),width=2)
    centered(draw,(960,998),'Each four-method panel: top row = LBFGS-Optim (Framewise), ScoreHMR; '
             'bottom row = Spline-Opt, Spline-Diff.',font(23))
    centered(draw,(960,1035),'Red: before refinement     Green: after refinement',font(24,True))
    # Resize static typography once, not on every video frame.
    return np.asarray(image.resize((1600,900),Image.Resampling.LANCZOS)),slots


def probe(path):
    with av.open(str(path)) as container:
        stream=container.streams.video[0]
        stream.codec_context.thread_count=1
        result=dict(width=stream.width,height=stream.height,fps=float(stream.average_rate),
                    codec=stream.codec_context.name,pixel_format=stream.codec_context.format.name)
        count=sum(1 for _ in container.decode(stream))
        result.update(frames=count,duration=count/result['fps'])
    return result


def faststart(path):
    atoms=[]
    with path.open('rb') as handle:
        while True:
            raw=handle.read(8)
            if len(raw)<8:break
            size,kind=struct.unpack('>I4s',raw)
            header=8
            if size==1:
                size=struct.unpack('>Q',handle.read(8))[0]
                header=16
            atoms.append(kind)
            if size==0:break
            handle.seek(size-header,1)
    return b'moov' in atoms and b'mdat' in atoms and atoms.index(b'moov')<atoms.index(b'mdat')


def export_video(z,spec,out):
    target=out/'videos'/f'{spec["name"]}_5mb.mp4'
    poster=out/f'{spec["name"]}_poster.webp'
    blobs=[z.read('ppt/media/'+name) for name in spec['media']]
    base,slots=background(spec)
    bitrate=4_350_000
    for attempt in range(4):
        print(f'[Compose slide {spec["slide"]}] attempt={attempt+1} bitrate={bitrate}',flush=True)
        with ExitStack() as stack:
            inputs=[stack.enter_context(av.open(BytesIO(data))) for data in blobs]
            streams=[c.streams.video[0] for c in inputs]
            for s in streams:
                if s.frames!=240 or s.average_rate!=Fraction(30):
                    raise RuntimeError('Unexpected timeline; do not resample silently')
                s.codec_context.thread_count=1
            decoders=[iter(c.decode(s)) for c,s in zip(inputs,streams)]
            container=stack.enter_context(av.open(str(target),'w',options={'movflags':'+faststart'}))
            stream=container.add_stream('libx264',rate=Fraction(30))
            stream.width,stream.height=1600,900
            stream.pix_fmt='yuv420p'
            stream.bit_rate=bitrate
            stream.codec_context.thread_count=1
            stream.options={'preset':'veryfast','maxrate':str(bitrate),'bufsize':str(bitrate*2)}
            for i in range(240):
                canvas=base.copy()
                for decoder,slot in zip(decoders,slots):
                    frame=next(decoder)
                    if abs(float(frame.pts*frame.time_base)-i/30)>.002:
                        raise RuntimeError('Source clips are not synchronized')
                    x,y,w,h=slot
                    canvas[y:y+h,x:x+w]=cv2.resize(frame.to_ndarray(format='rgb24'),(w,h),
                        interpolation=cv2.INTER_AREA if frame.height>h else cv2.INTER_LINEAR)
                if i==45:
                    Image.fromarray(canvas).resize((1280,720),Image.Resampling.LANCZOS).save(poster,quality=86,method=3)
                vf=av.VideoFrame.from_ndarray(canvas,format='rgb24')
                vf.pts=i;vf.time_base=Fraction(1,30)
                for packet in stream.encode(vf):container.mux(packet)
                if (i+1)%60==0:print(f'[Slide {spec["slide"]}] {i+1}/240 frames',flush=True)
            for decoder in decoders:
                if next(decoder,None) is not None:raise RuntimeError('Source has extra frames')
            for packet in stream.encode():container.mux(packet)
        if target.stat().st_size<CAP:break
        bitrate=int(bitrate*min(.85,4_300_000/target.stat().st_size))
    else:raise RuntimeError('Unable to meet strict 5MB limit')
    actual=probe(target)
    if (actual['frames'],actual['fps'],actual['codec'],actual['pixel_format'])!=(240,30.,'h264','yuv420p'):
        raise RuntimeError(f'Invalid output: {actual}')
    if not faststart(target):raise RuntimeError('Missing faststart atom ordering')
    record=dict(file=str(target.relative_to(ROOT)),slide=spec['slide'],bytes=target.stat().st_size,
        sha256=sha(target.read_bytes()),poster=str(poster.relative_to(ROOT)),**actual,
        sources=[dict(member='ppt/media/'+name,sha256=sha(data)) for name,data in zip(spec['media'],blobs)],
        synchronization='source timestamps checked frame-for-frame; no dropped frames',
        layout='clean guidance + four-method results, perturbed guidance + four-method results')
    print(f'[Verified] {target.name}: {record["bytes"]} bytes',flush=True)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pptx',type=Path,required=True)
    args=p.parse_args()
    out=ROOT/'assets'
    (out/'videos').mkdir(parents=True,exist_ok=True)
    cv2.setNumThreads(1)
    Image.MAX_IMAGE_PIXELS=160_000_000  # Known author-created 130MP PNG.
    images=[]
    with ZipFile(args.pptx) as z:
        for member,name,slide in (('image9.png','framewise_independent_updates.webp',3),
                                   ('image10.png','spline_shared_corrections.webp',4)):
            raw=z.read('ppt/media/'+member)
            with Image.open(BytesIO(raw)) as source:
                original=source.size
                factor=max(1,max(source.size)//2200)
                if original[0]*original[1]<25_000_000:
                    reduced=source.copy()
                else:
                    # libpng streams one row at a time and averages blocks.
                    # Never allocate the 130MP RGBA image in Python/Pillow.
                    with tempfile.TemporaryDirectory(prefix='splinehmr_png_') as tmp:
                        tmp=Path(tmp)
                        (tmp/'source.png').write_bytes(raw)
                        subprocess.run(['cc','-O2',str(Path(__file__).with_name('png_thumbnail.c')),
                                        '-lpng','-o',str(tmp/'thumbnail')],check=True)
                        subprocess.run([str(tmp/'thumbnail'),str(tmp/'source.png'),
                                        str(tmp/'reduced.ppm'),str(factor)],check=True)
                        with Image.open(tmp/'reduced.ppm') as small:
                            reduced=small.copy()
            reduced.thumbnail((2200,1600),Image.Resampling.LANCZOS)
            rgba=reduced.convert('RGBA')
            image=Image.new('RGB',rgba.size,'white')
            image.paste(rgba,mask=rgba.getchannel('A'))
            target=out/name
            image.save(target,format='WEBP',lossless=True,method=3)
            images.append(dict(file=str(target.relative_to(ROOT)),slide=slide,
                source_member='ppt/media/'+member,source_sha256=sha(raw),
                source_size=original,size=image.size,bytes=target.stat().st_size,
                sha256=sha(target.read_bytes())))
            reduced.close();rgba.close();image.close()
            print(f'[Diagram slide {slide}] {images[-1]["size"]}, {target.stat().st_size} bytes',flush=True)
        videos=[export_video(z,spec,out) for spec in SPECS]
    manifest=dict(source_presentation=args.pptx.name,source_sha256=sha(args.pptx.read_bytes()),
        diagrams=images,videos=videos,limit_bytes=CAP,
        resource_policy='serial; one codec/BLAS/OpenCV thread; no GPU; low-memory PNG reduction')
    (out/'presentation_media.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
