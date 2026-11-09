"""Print a pinned EXE-only command for owner review. Never execute it."""
from pathlib import Path
import sys,json,argparse
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S))
from in_place_packaging import digest,manifest_inputs,validate_build_locations

def plan(expected_manifest):
    if digest(S/'SOURCE_MANIFEST.sha256')!=expected_manifest:raise ValueError('The reviewed source manifest has changed')
    manifest_inputs(S);root=S.parent;r=root/'Recovery/VoiceRepair20261026'
    locations=validate_build_locations(S,r,r/'Offline GPT.inplace','Offline GPT.inplace')
    sdk=root/'Recovery/Engineering/reports/production-repair-20261021/sdk-build-input-env/Scripts/python.exe'
    if not sdk.is_file():raise ValueError('Retained SDK interpreter is unavailable')
    command=[str(sdk),'-I','-B','-X','pycache_prefix='+str(r/'Offline GPT.inplace-import-cache'),'-m','PyInstaller','--noconfirm','--workpath',str(r),'--distpath',str(r),str(S/'Offline GPT.inplace.spec')]
    return {'authorized':False,'commandExecuted':False,'workingDirectory':str(S),'command':command,'sourceManifestSha256':expected_manifest,'specSha256':digest(S/'Offline GPT.inplace.spec'),'interpreterSha256':digest(sdk),'locations':locations,'prerequisites':['Fresh relocated-destination owner authorization; this plan is not authorization','Normal application shutdown, fresh current SQLite recovery backup and protected EXE/UI rollback','Readiness receipts and full actual dependency compatibility PASS before EXE','Compiled-source acceptance then journaled EXE-last update and installed-path smoke acceptance'],'noCleanFlag':True,'noCollect':True,'nativeInferenceAuthorizedByThisPlan':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expected-manifest',required=True);args=parser.parse_args()
    print(json.dumps(plan(args.expected_manifest),indent=2))
