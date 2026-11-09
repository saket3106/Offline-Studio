"""Same-seed installed-runtime placement benchmark. Originals are read-only."""
import json,sys,subprocess,time,queue,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integrated_runtime import physical_memory_status,available_cuda_memory
from image_pipeline import ImageRunProfile
PKG=ROOT.parent/'Offline GPT';LOG=ROOT/'logs/comprehensive-sprint';OUT=LOG/'image-benchmark';OUT.mkdir(exist_ok=True)
cfg=json.loads((PKG/'offline_gpt_config.json').read_text())
def path(k):
    p=Path(cfg[k]);return p if p.is_absolute() else PKG/p
vram=available_cuda_memory();budget=max(2.5,min(5.5,vram/1024**3-1.8 if vram else 5.))
steps=28 if '--full' in sys.argv else 2
report={'steps':steps,'width':1280,'height':720,'seed':234567,'budgetGiB':budget,'runs':[],'sameSettingsExceptPlacement':True}
for placement in (('reference',) if '--reference' in sys.argv else ('disk','tuned') if '--full' in sys.argv else ('tuned',) if '--tune' in sys.argv else ('disk','auto')):
    profile=ImageRunProfile('benchmark-'+placement,physical_memory_status);profile.values['SAMPLING_STEP_COUNT']=steps
    target=OUT/f'{placement}-{steps}.png'
    command=[str(path('sd_cli')),'-t','0','--diffusion-model',str(path('flux_model')),'--vae',str(path('flux_vae')),'--llm',str(path('flux_encoder')),'-p','Generate a highly detailed red Ferrari sports car in 4K.','--cfg-scale','4','--sampling-method','euler','--steps',str(steps),'-W','1280','-H','720','--seed','234567','--vae-conv-direct','--vae-tiling','--diffusion-fa','--backend','cuda0','--max-vram',f'{budget:.1f}','-o',str(target)]
    command+=['--params-backend','disk'] if placement=='disk' else ['--auto-fit','on']
    if placement in ('tuned','reference'):
        command[command.index('--max-vram')+1]='5.5';command+=['--sage-attn']
    if placement=='reference':
        command[command.index('-p')+1]='Change only the paint of the black Porsche 911 to glossy red. Preserve the scene, car geometry, wheels, windows, lights and reflections.'
        command+=['-r',str(PKG/'generated/flux_20261009_140532_2c75b9.png')]
    started=time.perf_counter();profile.start_sampling();p=subprocess.Popen(command,cwd=path('sd_cli').parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));profile.process_ids.append(p.pid);lines=queue.Queue()
    def read():
        for line in p.stdout:lines.put(line)
        lines.put(None)
    threading.Thread(target=read,daemon=True).start();cancelled=False
    with (OUT/f'{placement}-{steps}.log').open('w',encoding='utf-8') as log:
        while True:
            if physical_memory_status().get('available',1024**3)<256*1024**2 or time.perf_counter()-started>720:
                p.terminate();cancelled=True;break
            try:line=lines.get(timeout=.2)
            except queue.Empty:continue
            if line is None:break
            log.write(line);log.flush();profile.line(line)
    code=p.wait(timeout=20);summary=profile.finish(OUT,'cancelled' if cancelled else 'success' if code==0 else 'failed')
    result={'placement':placement,'seconds':round(time.perf_counter()-started,3),'returnCode':code,'output':str(target),'command':command,'profile':summary};report['runs'].append(result)
    (OUT/f'comparison-{placement if placement in ("tuned","reference") else "placement"}-{steps}.json').write_text(json.dumps(report,indent=2));print(json.dumps(result),flush=True)
    if code:sys.exit(1)
print('COMPLETE',flush=True)
