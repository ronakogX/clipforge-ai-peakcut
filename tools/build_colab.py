"""Build a self-contained Colab notebook. The bundled processor needs no GitHub login."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

SETUP = r'''#@title 1. Prepare CLIPFORGE and connect Google Drive
import base64, hashlib, io, json, os, pathlib, shutil, subprocess, sys, zipfile
from google.colab import drive, files
from IPython.display import display, HTML, Video, clear_output
import ipywidgets as W
drive.mount('/content/drive')
BASE = pathlib.Path('/content/clipforge-colab')
BASE.mkdir(exist_ok=True)
payload = base64.b64decode("__BUNDLE__")
assert hashlib.sha256(payload).hexdigest() == '__SHA__', 'The bundled processor is damaged.'
with zipfile.ZipFile(io.BytesIO(payload)) as archive:
    for item in archive.infolist():
        target = (BASE / item.filename).resolve()
        if BASE.resolve() not in target.parents:
            raise RuntimeError('Unsafe source archive path')
        if not target.exists() or target.read_bytes() != archive.read(item):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
LIB = BASE / 'packages'
requirements = (BASE / 'requirements.txt').read_bytes()
fingerprint = hashlib.sha256(requirements).hexdigest()
marker = BASE / 'packages-ready.txt'
if not marker.exists() or marker.read_text() != fingerprint:
    print('Installing the video processor in an isolated folder. Your notebook packages stay unchanged.')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--quiet',
                    '--upgrade', '--target', str(LIB), '-r', str(BASE/'requirements.txt')], check=True)
    marker.write_text(fingerprint)
if not shutil.which('ffmpeg'):
    subprocess.run(['apt-get', 'update', '-qq'], check=True)
    subprocess.run(['apt-get', 'install', '-y', '-qq', 'ffmpeg', 'fonts-noto-core'], check=True)
WORK = BASE / 'runs'
WORK.mkdir(exist_ok=True)
DRIVE = pathlib.Path('/content/drive/MyDrive')
DESTINATION = DRIVE / 'CLIPFORGE' / 'Outputs'
DESTINATION.mkdir(parents=True, exist_ok=True)
ENV = dict(os.environ, DATABASE_URL='', PYTHONPATH=str(LIB)+os.pathsep+str(BASE), PEAKCUT_DATA=str(BASE/'state'),
           PEAKCUT_MODELS=str(BASE/'models'), PEAKCUT_UPDATE_CHECK='0', PEAKCUT_AI_KEY='', PEAKCUT_AI_KEY_FILE='',
           PEAKCUT_AI_MODELS='', PEAKCUT_ASR_URL='')
def run_worker(command, settings):
    import signal, uuid
    request = BASE / ('request-'+uuid.uuid4().hex+'.json')
    request.write_text(json.dumps(settings), encoding='utf-8')
    process = subprocess.Popen([sys.executable, str(BASE/'tools/colab_runner.py'), command, str(request)],
                               cwd=BASE, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, bufsize=1, start_new_session=True)
    try:
        for line in process.stdout:
            print(line, end='', flush=True)
        if process.wait() != 0:
            raise RuntimeError('Processing stopped. Read the error above. Finished Drive exports remain saved.')
    except KeyboardInterrupt:
        os.killpg(process.pid, signal.SIGTERM)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL)
        raise
print('Ready. English speech, up to 2 GiB per source. No paid AI key or GitHub setup is needed.')
'''

CONTROLS = r'''#@title 2. Open the clipping controls
import html, math
from PIL import Image, ImageDraw
state = {'folder': DRIVE, 'source': None, 'analysis': None}
wide = W.Layout(width='100%')
browser = W.Select(rows=7, layout=wide)
location = W.HTML()
chosen = W.HTML('<b>Choose your video below.</b>')
open_item = W.Button(description='Open folder / use video', layout=wide)
up = W.Button(description='Up one folder', layout=wide)
def refresh_folder():
    location.value = '<small>'+html.escape(str(state['folder'].relative_to(DRIVE) or 'My Drive'))+'</small>'
    entries = sorted(state['folder'].iterdir(), key=lambda p:(not p.is_dir(), p.name.casefold()))
    browser.options = [(('Folder: ' if p.is_dir() else 'Video: ')+p.name, str(p)) for p in entries
                       if p.is_dir() or p.suffix.lower() in ('.mp4','.mov','.mkv','.webm','.m4v','.avi','.ts')][:2000]
def open_choice(_):
    if not browser.value: return
    path = pathlib.Path(browser.value)
    if path.is_dir(): state['folder'] = path; refresh_folder()
    else:
        state['source'] = path
        chosen.value = '<b>Selected: '+html.escape(path.name)+'</b><br><small>'+str(round(path.stat().st_size/1024**2,1))+' MiB</small>'
def go_up(_):
    if state['folder'] != DRIVE:
        state['folder'] = state['folder'].parent
        refresh_folder()
open_item.on_click(open_choice); up.on_click(go_up)
refresh_folder()
count = W.Dropdown(options=[1,2,3,4,5,6,7,8], value=3, description='Highlights', layout=wide)
length = W.Dropdown(options=[15,30,45,60], value=45, description='Max seconds', layout=wide)
start = W.FloatText(value=0, description='From (sec)', layout=wide)
end = W.FloatText(value=0, description='To (0 = all)', layout=wide)
rights = W.Checkbox(value=False, description='I own this video or have permission to process it', indent=False, layout=wide)
analyze_button = W.Button(description='Analyze video', button_style='primary', layout=wide)
log_box = W.Output(layout=W.Layout(width='100%', max_height='320px', overflow='auto'))
editor = W.VBox(layout=wide)
results = W.VBox(layout=wide)
def show_results(data):
    controls = [W.HTML('<b>Saved to Google Drive:</b><br><code>'+html.escape(data['output_folder'])+'</code>')]
    preview = W.Output()
    for i, result in enumerate(data.get('outputs', [])):
        path = pathlib.Path(result['file'])
        label = result['aspect']+' · '+result['layout'].replace('_',' ')
        button = W.Button(description='Download MP4 '+str(i+1)+' · '+label, layout=wide)
        def download(_, p=path): files.download(str(p))
        button.on_click(download)
        controls.append(button)
    if data.get('outputs'):
        picker = W.Dropdown(options=[(str(i+1)+' · '+r['aspect']+' · '+r['layout'].replace('_',' '), r['file'])
                                      for i,r in enumerate(data['outputs'])], description='Preview', layout=wide)
        def play(change=None):
            path = pathlib.Path(picker.value)
            with preview:
                clear_output(wait=True)
                if path.stat().st_size <= 16*1024**2:
                    display(Video(str(path), embed=True, html_attributes='controls playsinline style="width:100%;max-height:520px"'))
                else: print('This preview is large. Use Download MP4 or open the saved file in Google Drive.')
        picker.observe(play,names='value')
        controls += [picker, preview]
        play()
    srt_files = list(pathlib.Path(data['output_folder']).glob('*.srt'))
    for path in srt_files:
        button = W.Button(description='Download captions · '+path.name, layout=wide)
        button.on_click(lambda _,p=path: files.download(str(p)))
        controls.append(button)
    if data.get('errors'): controls.append(W.HTML('<b>Some exports failed. See the processing log.</b>'))
    results.children = tuple(controls)
def build_editor(data):
    checks = [W.Checkbox(value=True, description=f"{i+1}. {c['start']:.1f}–{c['end']:.1f}s · {c['title'][:65]}", indent=False, layout=wide)
              for i,c in enumerate(data['highlights'])]
    aspect = W.Dropdown(options=[('9:16 · Vertical','9:16'),('16:9 · Landscape','16:9'),('Both shapes','both')], layout=wide)
    quality = W.Dropdown(options=[('360p · Fast draft',360),('720p · Balanced',720),('1080p · Sharper',1080)], layout=wide)
    style = W.Dropdown(options=[('Gaming Bold','bounce'),('Hype','hype'),('Minimal White','clean')], layout=wide)
    captions = W.Checkbox(value=True, description='Animated captions', indent=False)
    webcam = W.Dropdown(options=[('Automatic webcam','auto'),('Adjust webcam manually','manual'),('Gameplay only','none')], layout=wide)
    region = data.get('facecam')
    norms = [region[i]/data['info']['width' if i%2==0 else 'height'] for i in range(4)] if region else [0,0,.25,.25]
    coords = [W.FloatSlider(value=v,min=0 if i<2 else .02,max=1,step=.01,description=n,readout_format='.2f',layout=wide)
              for i,(n,v) in enumerate(zip(['X','Y','Width','Height'],norms))]
    share = W.FloatSlider(value=.35,min=.2,max=.6,step=.05,description='Webcam share',layout=wide)
    crop_picture = W.Output()
    def draw_box(change=None):
        with crop_picture:
            clear_output(wait=True)
            image = Image.open(data['thumbnail']).convert('RGB')
            box = region if webcam.value == 'auto' else None
            if webcam.value == 'manual':
                vals = [c.value for c in coords]
                box = [vals[i]*data['info']['width' if i%2==0 else 'height'] for i in range(4)]
            if box:
                x,y,w,h = box
                sx,sy = image.width/data['info']['width'],image.height/data['info']['height']
                ImageDraw.Draw(image).rectangle([x*sx,y*sy,(x+w)*sx,(y+h)*sy],outline='#b87aff',width=4)
            display(image)
    webcam.observe(draw_box,names='value')
    for coord in coords: coord.observe(draw_box,names='value')
    draw_box()
    manual_start = W.FloatText(value=data['analysis_start'],description='Manual from',layout=wide)
    manual_end = W.FloatText(value=0,description='To (0 = off)',layout=wide)
    render_button = W.Button(description='Render selected clips',button_style='success',layout=wide)
    def render_now(_):
        render_button.disabled = True; analyze_button.disabled = True
        manifest = pathlib.Path(data['work'])/'exports.json'
        with log_box:
            clear_output()
            try:
                run_worker('render',dict(analysis=str(pathlib.Path(data['work'])/'analysis.json'),
                    selected=[i for i,c in enumerate(checks) if c.value], aspect=aspect.value, quality=quality.value,
                    style=style.value,captions=captions.value,webcam_mode=webcam.value,
                    webcam=[c.value for c in coords],split_ratio=share.value,
                    manual_start=manual_start.value,manual_end=manual_end.value))
                show_results(json.loads(manifest.read_text()))
            except Exception as exc:
                print(str(exc))
                if manifest.exists(): show_results(json.loads(manifest.read_text()))
            finally: render_button.disabled = False; analyze_button.disabled = False
    render_button.on_click(render_now)
    editor.children = tuple([W.HTML('<h3>Choose highlights</h3><small>Ranking uses speech boundaries and audio loudness, with no paid AI calls.</small>')]+checks+
        [W.HTML('<h3>Output</h3>'),aspect,quality,style,captions,
         W.HTML('<h3>Webcam</h3><small>Both stacked orders are generated when a webcam is set. Otherwise the output is gameplay only. For manual crops, X + Width and Y + Height must each be at most 1.</small>'),
         webcam,crop_picture,*coords,share,W.HTML('<h3>Optional extra clip</h3><small>Enter an end time to add a manual interval within the analyzed range (3–180 seconds).</small>'),
         manual_start,manual_end,render_button])
def analyze_now(_):
    if not state['source']:
        chosen.value = '<b>Select a video first.</b>'; return
    if not rights.value:
        chosen.value = '<b>Confirm that you own the video or have processing permission.</b>'; return
    analyze_button.disabled = True; editor.children = (); results.children = ()
    with log_box:
        clear_output()
        try:
            run_worker('analyze',dict(source=str(state['source']),work_root=str(WORK),output_root=str(DESTINATION),
                                      count=count.value,duration=length.value,start=start.value,end=end.value))
            data = json.loads((WORK/'latest.json').read_text())
            state['analysis'] = data
            build_editor(data)
        except Exception as exc: print(str(exc))
        finally: analyze_button.disabled = False
analyze_button.on_click(analyze_now)
display(W.VBox([W.HTML('<h2>CLIPFORGE AI</h2><p>Upload your video to Google Drive, choose it here, and analyze. English speech is supported in this version. Use the notebook stop button to cancel processing.</p>'),
                location,browser,open_item,up,chosen,count,length,start,end,rights,analyze_button,log_box,editor,results],layout=wide))
'''


def build():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        files = list((ROOT/'studio').rglob('*.py'))+list((ROOT/'studio/fonts').glob('*'))
        files += [ROOT/'requirements.txt',ROOT/'LICENSE',ROOT/'tools/colab_runner.py']
        for path in files:
            if path.is_file(): archive.write(path,path.relative_to(ROOT))
    payload = buffer.getvalue()
    setup = SETUP.replace('__BUNDLE__',base64.b64encode(payload).decode()).replace('__SHA__',hashlib.sha256(payload).hexdigest())
    cells = []
    def markdown(source): cells.append(dict(id=f'clipforge-{len(cells)}',cell_type='markdown',metadata={},source=source.splitlines(keepends=True)))
    def code(source):
        ast.parse(source)
        cells.append(dict(id=f'clipforge-{len(cells)}',cell_type='code',execution_count=None,metadata={'cellView':'form'},outputs=[],source=source.splitlines(keepends=True)))
    markdown('''# CLIPFORGE AI — phone clipping notebook

**No GitHub account, Codespaces or paid AI key is needed.** This is an interactive notebook, not an always-on website.

1. Upload your authorized video to **Google Drive** (up to 2 GiB).
2. Choose **Runtime → Run all** and approve Google's Drive connection when prompted.
3. Use the video picker, tap **Analyze video**, select highlights and tap **Render selected clips**.

Finished MP4s and SRT captions are saved under **My Drive / CLIPFORGE / Outputs**. You can also preview and download them here.
The first run installs packages and downloads the English speech model (about 480 MB). Use the standard free CPU runtime; no paid upgrade is required.
Free Colab availability and session duration are limited. A disconnected runtime may lose unfinished work; already saved Drive exports remain.

English transcription is implemented. Hindi/Hinglish speech recognition is not included in this version. Webcam detection is a geometric heuristic; review the box or adjust it using the crop sliders. Hidden gameplay pixels cannot be restored.

Source: CLIPFORGE's tested PeakCut adaptation, based on the MIT-licensed PeakCut project by haziqahmedqasmi. Speech model: NVIDIA Parakeet TDT 0.6b v2, CC BY 4.0. No sample clips or fake progress are used.
''')
    code(setup)
    code(CONTROLS)
    notebook=dict(nbformat=4,nbformat_minor=5,metadata={'colab':{'name':'CLIPFORGE AI.ipynb','provenance':[]},
                    'kernelspec':{'display_name':'Python 3','name':'python3'},'language_info':{'name':'python'}},cells=cells)
    destination=ROOT/'notebooks/CLIPFORGE_AI.ipynb'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
    print(f'Notebook: {destination} ({destination.stat().st_size:,} bytes)')
    print('Bundled source SHA256:',hashlib.sha256(payload).hexdigest())
    return destination


if __name__=='__main__': build()
