"""Seal this bounded review and retain prior native/source checkpoint evidence."""
from pathlib import Path
import ast,hashlib,json,os,sqlite3,sys,time,unittest,zipfile,io
S=Path(__file__).resolve().parents[1];F=S.parent;V=F/'Documentation/VoiceRepair20261026';R=F/'Recovery/VoiceRepair20261026';sys.path[:0]=[str(S),str(S/'tests')]
os.environ['OFFLINE_GPT_DATA_DIR']=str(R/'unit-profile');os.environ['QT_QPA_PLATFORM']='offscreen'
from in_place_packaging import digest,manifest_inputs,runtime_modules,code_identity
from packaging_readiness import table_digests

prior=json.loads((V/'SOURCE_MANIFEST_AFTER.json').read_text());before=json.loads((V/'BEFORE.json').read_text());initial=json.loads((V/'READINESS_INITIAL.json').read_text());journal=json.loads((V/'JOURNAL_DISPOSITION.json').read_text())
voice_files=['app.py','live_voice.py','voice_runtime.py','integrated_runtime.py','agent_desktop.py','frontend-source/src/main.jsx','frontend-source/src/styles.css','frontend-source/src/voiceCapture.js','ui/assets/index.js','ui/assets/index.css']
assert all(digest(S/n)==prior[n] for n in voice_files),'A proven application component changed unexpectedly'
patterns=['test_in_place_packaging.py','test_live_voice_session.py','test_speech_journal.py','test_relocated_resource_paths.py']
suite=unittest.TestSuite(unittest.defaultTestLoader.discover(str(S/'tests'),pattern=p) for p in patterns);start=time.perf_counter();output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
tests={'scope':'Focused deterministic packaging guards, unchanged voice state/exit/journal and relocated resources; zero native calls','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),'seconds':round(time.perf_counter()-start,3),'patterns':patterns,'status':'PASS' if result.wasSuccessful() else 'FAIL'}
(V/'READINESS_TESTS.log').write_text(output.getvalue(),encoding='utf-8');(V/'READINESS_TESTS.json').write_text(json.dumps(tests,indent=2),encoding='utf-8');assert result.wasSuccessful(),output.getvalue()

# Reconcile the stronger code-identity comparison against the actual retained
# stdlib without generating a new ZIP or invoking any packaging machinery.
base_matches=[];base=F/'Application/base_library.zip'
with zipfile.ZipFile(base) as z:
 for name in z.namelist():
  if not name.endswith('.pyc'):continue
  import marshal
  p=Path(sys.base_prefix)/'Lib'/name[:-1]
  base_matches.append(code_identity(marshal.loads(z.read(name)[16:]))==code_identity(compile(p.read_bytes(),str(p),'exec',dont_inherit=True,optimize=0)))
assert len(base_matches)==155 and all(base_matches)

doc='''# One controlled in-place update — current readiness, 26 October 2026

Canonical source: C:\\Users\\mesak\\Documents\\OfflineGPT\\Source.
Only installed target: C:\\Users\\mesak\\Documents\\OfflineGPT\\Application\\Offline GPT.exe.

No build or installation is authorized by this document. Native pilot/source
results do not mean the installed executable contains the repairs.

Current evidence is Documentation/VoiceRepair20261026/READINESS_REPORT.md and
READINESS_CHECKPOINT.json. The prior REPORT.md/native receipts remain intact.
The installed EXE is b38e3b013905d0f857e02e4c036e1d957c6eddac19a6c243e31e6b048459dd2c.

The historical speech journal anomaly is retained, not corrected. The installed
callback demonstrably permits success-to-cancelled reclassification in a
synthetic SQLite fixture. Its actual production writer is not established.
No authoritative replacement completion timestamp exists. Preserve the current
row and both audit snapshots; any production-data correction requires separate
explicit owner approval. Never restore the old DB over newer work.

## Procedure after fresh relocated-destination authorization

1. Recheck current manifest, EXE/config hashes, resource paths, free disk/RAM and
   intervening user work. Print the pinned command with tools/prepare_in_place_build.py
   --expected-manifest <reviewed SHA-256>. This tool only prints; it cannot build.
2. Confirm normal app shutdown and descendant exit. Never force-close user apps.
   Preserve current EXE, only ui/assets/index.js and index.css, config bytes and
   a consistent current SQLite online backup including committed WAL, in the
   existing private Recovery location. Record hashes and fsync a replacement journal.
3. Use only the printed retained-SDK command and reviewed Offline GPT.inplace.spec.
   No --clean, caller-supplied paths, legacy .bat, standard spec or COLLECT.
   The spec pins work/output to Recovery/VoiceRepair20261026; it rejects an existing
   EXE, stale work/import cache, prior build receipts, redirected paths and source drift.
   PyInstaller may create directories before executing a spec, so never improvise
   a direct command with production paths or --clean. The fixed command is required.
4. One authorized analysis/build attempt only. Before EXE, actual Analysis must
   include every manifest-derived application module and current frontend asset,
   without shadowing. All retained external files, frozen dependency code and
   executable hooks must match. Differing/new native inputs are NOT authorized.
   Stop on failure and retain logs; do not copy DLLs or weaken a gate to continue.
5. After EXE, verify every compiled canonical/dependency module and executable
   script, plus unchanged source/native/installed inputs. Full collected dependency
   closure and genuine compiled acceptance are still unverified until this runs.
6. Recheck production shutdown and all declared hashes immediately before update.
   Stage and flush only the declared EXE/UI replacements in the existing layout.
   Journal each step and replace EXE last. Do not replace native dependencies,
   models, configuration, user DB, images, documents or licence assets.
7. Run bounded actual installed-path Qt/React/bridge, Model Manager, voice state,
   Agent permission/cancel, history/Library/settings and normal-shutdown smoke tests.
   Use an isolated profile for synthetic writes. No inference or microphone calls
   are implied by deployment permission; obtain scoped fresh authorization for those.
8. On failure, restore only declared application EXE/UI files using the journal.
   Keep newer DB changes and failure evidence. After success, inventory transient
   build files before any bounded cleanup; do not create a second application root.

Half duplex remains the accepted design. Orb interruption is available; no
full-duplex acoustic claim. Spoken resume cannot work while physically muted.
The observed exit alias has deterministic coverage but no fresh acoustic retest.
No GitHub, CI, candidate application, download, folder consolidation or automation.
'''
(S/'docs/IN_PLACE_UPDATE.md').write_text(doc,encoding='utf-8')

names=set(prior);names.add('packaging_readiness.py')
names.update(str(p.relative_to(S)).replace('\\','/') for p in (S/'tools').glob('*.py'))
current={n:digest(S/n) for n in sorted(names)};changes={n:{'previous':prior.get(n),'current':h} for n,h in current.items() if prior.get(n)!=h}
manifest=S/'SOURCE_MANIFEST.sha256';manifest.write_text('# OfflineGPT native voice deployment readiness, 26 October 2026; no build or install.\n'+''.join(h+'  '+n+'\n' for n,h in current.items()),encoding='utf-8')
assert manifest_inputs(S)==current
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('readonly_build_plan',S/'tools/prepare_in_place_build.py');planner=module_from_spec(spec);spec.loader.exec_module(planner)
plan=planner.plan(digest(manifest));(V/'REVIEWED_EXE_ONLY_PLAN.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')

with sqlite3.connect((F/'Application/offline_gpt.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
 db.execute('BEGIN');now=table_digests(db);integrity=db.execute('PRAGMA quick_check').fetchall()==[('ok',)];db.rollback()
assert integrity and now==journal['productionTableDigests'],'New production drift during review; do not clear preservation'
assert digest(F/'Application/Offline GPT.exe')==initial['installedExeSha256'] and digest(F/'Application/offline_gpt_config.json')==before['configSha256']
zip_path=R/'packaging-review-verified.zip'
with zipfile.ZipFile(zip_path,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for n in changes:z.write(S/n,n)
 z.write(manifest,'SOURCE_MANIFEST.sha256')
with zipfile.ZipFile(zip_path) as z:assert all(hashlib.sha256(z.read(n)).hexdigest()==current[n] for n in changes)
(V/'READINESS_SOURCE_MANIFEST.json').write_text(json.dumps(current,indent=2),encoding='utf-8')
state={'status':'PREPARED_NOT_BUILT_NOT_INSTALLED','sourceManifestSha256':digest(manifest),'sourceFiles':len(current),'changesSinceAcceptedVoiceCheckpoint':changes,'provenVoiceFilesUnchanged':{n:current[n] for n in voice_files},'tests':tests,'selectedDependencyExactMatches':len(initial['selectedDependencyChecks']),'stdlibSemanticMatches':len(base_matches),'fullPackagingDependencyClosure':'NOT_CLEARED; actual Analysis and compiled verification await fresh authorization','requiredCanonicalRuntimeModules':sorted(runtime_modules(S,current)),'productionTablesUnchangedDuringThisReview':True,'historicalProductionJournalExceptionRetained':True,'installedExeSha256':digest(F/'Application/Offline GPT.exe'),'installedConfigUnchanged':True,'rollbackArchive':str(zip_path),'rollbackArchiveSha256':digest(zip_path),'buildPlan':str(V/'REVIEWED_EXE_ONLY_PLAN.json'),'builds':0,'installations':0,'nativeCalls':0}
(V/'READINESS_CHECKPOINT.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
report=f'''# OfflineGPT — final native voice checkpoint and deployment readiness

26 October 2026. **PREPARED, NOT BUILT OR INSTALLED. Full packaging compatibility is NOT CLEARED.**

- Source manifest: `{state['sourceManifestSha256']}`; {len(current)} files. Exact old/new changed-file identities: READINESS_CHECKPOINT.json. Full manifest: READINESS_SOURCE_MANIFEST.json and Source/SOURCE_MANIFEST.sha256.
- Proven voice/model/UI components are byte-identical to the accepted voice checkpoint. No voice redesign, frontend rebuild, model change or repeated native test. {tests['tests']} focused deterministic tests passed, zero failures/skips in {tests['seconds']} seconds; earlier 76 source and 49 desktop checks remain their original distinct evidence, not new installed-app acceptance.
- Journal row `56cf110e-9106-4cf9-b4c0-183c99e1281e` remains cancelled with finished epoch `1792956569.4217255`; before snapshot was success with finished epoch `1792937367.95651`. The actual installed callback reproduced success→cancelled on Stop in an in-memory fixture; repaired source retained success. This demonstrates the defect, not writer attribution. No correction recommended without authoritative evidence. No fabricated timestamp or DB restore. Any production-data correction needs separate explicit approval. All 34 current table digests stayed unchanged during this review; all 33 non-journal tables still match the original baseline. Historical exception is retained, not erased or relabeled as exact original preservation.
- Packaging review repaired unpinned output/work locations, missing/shadowed module detection, incomplete/swapped frontend detection, namespace handling, stale-cache/evidence reuse, unreviewed runtime hooks and input/compiled dependency drift checks. No COLLECT exists. The approved future command has fixed private transient paths and no --clean; compilation cannot target Application through that command/spec. Arbitrary unapproved PyInstaller arguments are outside this procedure; its CLI can create/clean paths before a spec runs.
- Static retained-input review: **{len(initial['selectedDependencyChecks'])}/{len(initial['selectedDependencyChecks'])} Python/SQLite/Qt files match exact installed bytes; 155/155 stdlib code identities match.** Consolidated resource paths checked from both Source and Application. Required runtime modules: {len(state['requiredCanonicalRuntimeModules'])}, including live_voice, voice_runtime, Model Manager and Agent modules. The manifest-derived hidden-import/data requirements are enforced; actual collected and compiled inclusion is NOT yet established.
- **Full dependency outcome: NOT CLEARED.** No actual PyInstaller Analysis, executable hook/complete dependency collection, transitive/dynamic native compatibility acceptance or post-build compiled check has run. The new guards are deterministic-tested, not proof of an actual artifact. No DLL/runtime replacement is approved. Actual discrepancies must stop before EXE construction. Current bundled specialist engines are not changed; no new native compatibility claim.
- Unresolved live behavior: deliberate half duplex; click orb to interrupt. No acoustic full-duplex claim. A muted mic cannot recognize Resume; use its control. Observed mode→model exit alias has deterministic coverage, not another live retest. Ten turns were synthetic Qt; physical pilot had four conversational turns. Long/noisy sessions, accents/device switching and extended microphone/speaker reliability remain unverified. Owner-confirmed clear playback/automatic listening from prior pilot remains accepted evidence.
- Fresh native authorization is required for any further mic/speaker acceptance, post-install Qwen/Whisper/Kokoro runs, sustained speech sessions and acoustic interruption experiments. GPT-OSS/vision/FLUX/UHD/14B are not part of this readiness review. No such workload ran.
- Installed EXE remains `{state['installedExeSha256']}`. Settings/config unchanged; no production data was corrected, replaced or restored. Current DB integrity passes. Existing old/current source, SQLite recovery backup and minimal packaging-before/after ZIPs remain recoverable. Project structure preserved; no broad storage scan or cleanup, GitHub/CI, candidate tree, model download or automation.

The next authorized milestone is one compatibility-gated local EXE-only build and journaled in-place update. It requires fresh owner approval for the relocated Application target, current hash/data/resource/memory/disk and normal-shutdown checks, a fresh consistent SQLite backup and EXE/two-UI rollback, actual dependency PASS, compiled identity PASS, then installed-path smoke acceptance. Preserve the current historical journal row in that backup; do not repair it implicitly. No deployment is authorized by this report.

Exact printable command/inputs: REVIEWED_EXE_ONLY_PLAN.json (commandExecuted=false, authorized=false). Procedure: Source/docs/IN_PLACE_UPDATE.md. Proposed production replacements remain **Offline GPT.exe, ui/assets/index.js and ui/assets/index.css only**, executable last. Never overwrite DLLs, models, config, user DB, Library or licensing assets. On failure restore declared EXE/UI only; preserve newer user data.

New source files are bounded read-only audit/command-preparation tools; builder helpers are excluded from runtime requirements. Changes this review:
'''+''.join('- `'+n+'`\n' for n in changes)+f'\nVerified changed-source checkpoint SHA-256: `{state["rollbackArchiveSha256"]}`.\n'
(V/'READINESS_REPORT.md').write_text(report,encoding='utf-8')
print(json.dumps({k:v for k,v in state.items() if k not in {'changesSinceAcceptedVoiceCheckpoint','provenVoiceFilesUnchanged','requiredCanonicalRuntimeModules'}},indent=2))
