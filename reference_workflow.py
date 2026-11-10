"""Selected visual references and explicit pixel-preserving local composition.

No model download, automatic segmentation, web execution or generation claim.
The existing FluxWorker remains the owner of native image inference.
"""
from pathlib import Path
import hashlib,io,json,math,os,re,time,uuid

MAX_REFERENCE_BYTES=20_000_000
MAX_REFERENCE_PIXELS=20_000_000


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():raise InterruptedError('Reference operation cancelled.')


def _regular(raw,require_file=True):
    path=Path(raw).absolute()
    for part in [path,*path.parents]:
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise PermissionError('Redirected reference paths are unavailable.')
    path=Path(os.path.abspath(path))
    for part in [path,*path.parents]:
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise PermissionError('Redirected reference paths are unavailable.')
    if require_file and not path.is_file():raise FileNotFoundError('Selected reference file is unavailable.')
    return path


def _sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def _image(path,cancel=None):
    from PIL import Image,ImageOps
    path=_regular(path)
    if path.stat().st_size>MAX_REFERENCE_BYTES:raise ValueError('Selected raster exceeds the 20 MB reference limit.')
    _cancelled(cancel)
    with Image.open(path) as image:
        if image.format not in {'PNG','JPEG','WEBP'}:raise ValueError('Choose a PNG, JPEG or WebP raster reference.')
        if image.width<1 or image.height<1 or image.width*image.height>MAX_REFERENCE_PIXELS:raise ValueError('Selected raster exceeds the 20 megapixel reference limit.')
        image.load();result=ImageOps.exif_transpose(image).convert('RGB')
    _cancelled(cancel)
    return result


def working_reference(path,cache_dir,max_side=2048):
    """The image itself when it is within the reference limits, else a cached PNG copy scaled to max_side.

    Large results (a 3840x2160 PNG is ~25 MB) exceed MAX_REFERENCE_BYTES; the edit canvas is <=1024 px, so a
    2048 px copy keeps every detail the edit can use. Copies are keyed by the source bytes and reused."""
    from PIL import Image,ImageOps
    source=_regular(path)
    with Image.open(source) as image:
        size=image.size;fmt=image.format
    if source.stat().st_size<=MAX_REFERENCE_BYTES and max(size)<=max_side and fmt in {'PNG','JPEG','WEBP'}:return source
    folder=_regular(cache_dir,False);folder.mkdir(parents=True,exist_ok=True)
    target=folder/(_sha(source)[:32]+f'-{max_side}.png')
    if target.is_file():return _regular(target)
    with Image.open(source) as image:
        if image.width*image.height>4*MAX_REFERENCE_PIXELS:raise ValueError('Selected raster is too large to edit.')
        picture=ImageOps.exif_transpose(image).convert('RGB')
    picture.thumbnail((max_side,max_side),Image.LANCZOS)
    partial=target.with_suffix('.part');picture.save(partial,format='PNG');partial.replace(target)
    return _regular(target)


def prepare_reference(path,cache_dir,source_metadata=None,cancel=None):
    """Normalize actual selected bytes into an immutable content-addressed PNG."""
    source=_regular(path);raw_hash=_sha(source);image=_image(source,cancel);folder=_regular(cache_dir,False);folder.mkdir(parents=True,exist_ok=True)
    stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue();image_hash=hashlib.sha256(data).hexdigest();target=folder/(image_hash+'.png')
    if target.exists():
        _regular(target)
        if _sha(target)!=image_hash:raise ValueError('Cached reference bytes differ from their recorded identity.')
    else:
        _cancelled(cancel)
        try:
            with target.open('xb') as handle:handle.write(data)
        except FileExistsError:
            if _sha(_regular(target))!=image_hash:raise ValueError('Reference cache identity collision.')
    metadata=source_metadata or {}
    return {**metadata,'path':str(target),'sourcePath':str(source),'sourceHash':raw_hash,'imageHash':image_hash,'contentFingerprint':image_hash,'width':image.width,'height':image.height,'status':'SAVED_REFERENCE','conditioningActive':False}


class ReferenceStore:
    """Additive, project-scoped metadata over the existing workspace connection."""
    def __init__(self,workspace):
        self.ws=workspace;self.con=workspace.con;self.lock=workspace.lock;self.directory=Path(workspace.directory)
        with self.lock,self.con:
            self.con.execute('CREATE TABLE IF NOT EXISTS studio_references(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,run_id TEXT,source_id TEXT,source_url TEXT,image_url TEXT,license TEXT,artist TEXT,local_path TEXT,image_hash TEXT,source_hash TEXT,width INTEGER,height INTEGER,created REAL,expires REAL,metadata TEXT)')
            self.con.execute('CREATE UNIQUE INDEX IF NOT EXISTS studio_reference_identity ON studio_references(project_id,image_hash)')
    def add(self,record,project='',run_id='',days=30,approved_path=False):
        from research_network import canonical_url
        path=_regular(record.get('path',''));cache=(self.directory/'knowledge'/'references').absolute()
        if not approved_path and not path.is_relative_to(cache):raise PermissionError('Import references through the selected-source picker or download cache.')
        image=_image(path);image_hash=_sha(path);claimed=record.get('imageHash')
        if claimed and image_hash!=claimed:raise ValueError('Reference changed after preparation.')
        source_hash=record.get('sourceHash') or record.get('contentFingerprint') or image_hash
        if not re.fullmatch('[0-9a-f]{64}',str(source_hash)):raise ValueError('Reference source hash is invalid.')
        source_url=record.get('sourceUrl') or record.get('source_url') or ''
        image_url=record.get('url') or record.get('imageUrl') or ''
        if source_url:source_url=canonical_url(source_url)
        if image_url:image_url=canonical_url(image_url)
        metadata={key:record[key] for key in ['title','sourceTitle','alt','licenseUrl','credit','attributionRequired','restrictions','provider','metadataId','runId','sourceId'] if key in record}
        now=time.time();expiry=now+max(1,min(365,int(days)))*86400
        with self.lock,self.con:
            existing=self.con.execute('SELECT id FROM studio_references WHERE project_id=? AND image_hash=?',(project,image_hash)).fetchone();ident=existing[0] if existing else uuid.uuid4().hex
            self.con.execute('INSERT INTO studio_references VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,image_hash) DO UPDATE SET run_id=excluded.run_id,source_id=excluded.source_id,source_url=excluded.source_url,image_url=excluded.image_url,license=excluded.license,artist=excluded.artist,local_path=excluded.local_path,expires=excluded.expires,metadata=excluded.metadata',(ident,project,run_id or record.get('runId',''),record.get('sourceId',''),source_url,image_url,str(record.get('license','Not established'))[:1000],str(record.get('artist',''))[:1000],str(path),image_hash,source_hash,image.width,image.height,now,expiry,json.dumps(metadata,ensure_ascii=False)))
        return self.get(ident,project)
    def list(self,project=''):
        with self.lock:rows=self.con.execute('SELECT * FROM studio_references WHERE project_id=? ORDER BY created DESC LIMIT 100',(project,)).fetchall()
        return [self._row(row) for row in rows]
    def _row(self,row):
        result=dict(zip(['id','projectId','runId','sourceId','sourceUrl','url','license','artist','path','imageHash','sourceHash','width','height','created','expires','metadata'],row));result['metadata']=json.loads(result['metadata'] or '{}');result['conditioningActive']=False
        path=Path(result['path']);result['state']='expired' if result['expires']<time.time() else 'saved'
        try:
            path=_regular(path)
            if path.stat().st_size>MAX_REFERENCE_BYTES or _sha(path)!=result['imageHash']:result['state']='changed'
        except (OSError,PermissionError):result['state']='missing'
        return result
    def get(self,ident,project=''):
        with self.lock:row=self.con.execute('SELECT * FROM studio_references WHERE id=? AND project_id=?',(ident,project)).fetchone()
        if row is None:raise PermissionError('Selected reference is unavailable in this project.')
        result=self._row(row)
        if result['state']!='saved':raise ValueError('Selected reference is '+result['state']+'; select or refresh it before reuse.')
        return result
    def remove(self,ident,project=''):
        with self.lock,self.con:self.con.execute('DELETE FROM studio_references WHERE id=? AND project_id=?',(ident,project))
        return {'removed':True,'originalFilePreserved':True}


def reference_capabilities(config,cli_help='',native_flags=None):
    model=Path(str(config.get('flux_model','')));name=model.name.casefold().replace('-','')
    documented_family='flux2' in name and 'klein' in name
    flags=set(re.findall(r'--?[a-z][a-z0-9-]*',str(cli_help)))
    if native_flags is not None:flags.update(str(flag) for flag in native_flags)
    native_flag=bool({'-r','--ref-image'}&flags)
    return {'model':str(model),'modelExists':model.is_file(),'documentedFamily':'FLUX.2 Klein' if documented_family else 'not identified','nativeReferenceFlag':native_flag,'nativeFlags':sorted(flags),'flagSource':'installed CLI help probe' if native_flags is not None else 'supplied help text' if cli_help else 'not probed','referenceEditing':'AVAILABLE_REQUIRES_NATIVE_ACCEPTANCE' if documented_family and native_flag and model.is_file() else 'UNAVAILABLE_OR_NOT_PROBED','conditioningMethod':'stable-diffusion.cpp -r / --ref-image actual raster input','subjectPreservingComposite':'EXPLICIT_MASK_OR_RECTANGLE_CPU','automaticSegmentation':False,'adapterWeightsInstalledByThisFeature':False,'inferenceVerified':False}


def conditioning_evidence(reference,command):
    """Prove the actual reference argv/file link; process success is separate evidence."""
    path=_regular(reference['path']);actual=_sha(path)
    if reference.get('imageHash') and actual!=reference['imageHash']:raise ValueError('Reference hash changed before native dispatch.')
    used=[]
    for index,value in enumerate(command[:-1]):
        if value in {'-r','--ref-image'} and _regular(command[index+1])==path:used.append(str(path))
    if not used:raise ValueError('Selected reference is not an actual native image argument.')
    _image(path)
    return {'method':'FLUX2_NATIVE_REFERENCE_ARGUMENT','referencePath':str(path),'referenceSha256':actual,'sourceUrl':reference.get('sourceUrl',''),'imageUrl':reference.get('url',''),'license':reference.get('license','Not established'),'actualImageArgument':True,'inferenceVerified':False,'conditioningClaim':'Actual raster supplied to native reference input; generated-output acceptance is still required.'}


def composite_subject(reference_path,background_path,output_dir,*,mask_path=None,rectangle=None,cancel=None):
    """Preserve explicitly selected original pixels over a chosen background.

    Rectangle coordinates are original-image pixels. A reviewed grayscale mask
    preserves its 255 pixels exactly; intermediate values blend at the boundary.
    No inferred subject segmentation or generative model is involved.
    """
    from PIL import Image,ImageDraw
    started=time.perf_counter();_cancelled(cancel)
    if bool(mask_path)==(rectangle is not None):raise ValueError('Choose exactly one explicit subject mask or rectangle.')
    source=_regular(reference_path);background_source=_regular(background_path);foreground=_image(source,cancel);background=_image(background_source,cancel)
    if background.size!=foreground.size:background=background.resize(foreground.size,Image.Resampling.LANCZOS)
    if mask_path:
        selected=_regular(mask_path)
        if selected.stat().st_size>MAX_REFERENCE_BYTES:raise ValueError('Mask exceeds the reference byte limit.')
        with Image.open(selected) as raw:
            if raw.format not in {'PNG','JPEG','WEBP'} or raw.size!=foreground.size:raise ValueError('Mask must be a supported raster with exactly the source dimensions.')
            raw.load();mask=raw.convert('L')
        mask_source={'path':str(selected),'sha256':_sha(selected)}
    else:
        if not isinstance(rectangle,(tuple,list)) or len(rectangle)!=4 or any(type(v) is not int for v in rectangle):raise ValueError('Rectangle must contain four integer pixel coordinates.')
        left,top,right,bottom=rectangle
        if not (0<=left<right<=foreground.width and 0<=top<bottom<=foreground.height):raise ValueError('Selected rectangle must lie inside the reference.')
        mask=Image.new('L',foreground.size,0);ImageDraw.Draw(mask).rectangle((left,top,right-1,bottom-1),fill=255);mask_source={'rectangle':list(rectangle)}
    histogram=mask.histogram();preserved=histogram[255]
    if not preserved or histogram[0]==0:raise ValueError('Select a nonempty subject region and leave some background outside it.')
    _cancelled(cancel);result=Image.composite(foreground,background,mask)
    # Exact selected-pixel identity is verified independently of the saved format.
    import numpy as np
    opaque=np.asarray(mask)==255;original_pixels=np.asarray(foreground)[opaque].tobytes();output_pixels=np.asarray(result)[opaque].tobytes()
    if original_pixels!=output_pixels:raise RuntimeError('Subject preservation verification failed.')
    _cancelled(cancel);folder=_regular(output_dir,False);folder.mkdir(parents=True,exist_ok=True);target=folder/('subject-composite-'+uuid.uuid4().hex+'.png');partial=target.with_suffix('.partial')
    try:
        with partial.open('xb') as handle:result.save(handle,format='PNG')
        _cancelled(cancel)
        with Image.open(partial) as saved:
            saved.load()
            if np.asarray(saved.convert('RGB'))[opaque].tobytes()!=original_pixels:raise RuntimeError('Saved PNG did not preserve selected subject pixels.')
        partial.replace(target)
    finally:
        if partial.exists():partial.unlink()
    provenance={'method':'EXPLICIT_SUBJECT_PIXEL_COMPOSITE','generativeModelUsed':False,'automaticSegmentationUsed':False,'referencePath':str(source),'referenceSha256':_sha(source),'backgroundPath':str(background_source),'backgroundSha256':_sha(background_source),'outputSha256':_sha(target),'mask':mask_source,'preservedOpaquePixels':preserved,'blendedBoundaryPixels':sum(histogram[1:255]),'selectedPixelSha256':hashlib.sha256(original_pixels).hexdigest(),'selectedPixelsExactlyPreserved':True,'created':time.time(),'durationMs':round((time.perf_counter()-started)*1000,2)}
    receipt=target.with_suffix('.json')
    with receipt.open('x',encoding='utf-8') as handle:json.dump(provenance,handle,indent=2,ensure_ascii=False)
    return {'path':str(target),'dimensions':f'{foreground.width} × {foreground.height}','parentPath':str(source),'operation':'subjectComposite','method':'Subject-preserving composition · explicit reviewed region · no generative model','provenancePath':str(receipt),'metrics':provenance}
