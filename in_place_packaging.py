"""Fail-closed EXE-only compatibility gate. No installer, file replacement or COLLECT.

Used only by the owner-approved local spec; it never copies dependencies.
"""
from pathlib import Path
from runtime_contracts import windows_payload_path,validate_windows_payload_paths
import hashlib,json,marshal,types,zipfile,os

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def code_identity(code):
    if isinstance(code,types.CodeType):
        return (code.co_name,code.co_qualname,code.co_argcount,code.co_posonlyargcount,code.co_kwonlyargcount,
                code.co_nlocals,code.co_stacksize,code.co_flags,code.co_code,
                tuple(code_identity(c) for c in code.co_consts),code.co_names,
                code.co_varnames,code.co_freevars,code.co_cellvars,code.co_exceptiontable)
    return code

BUILD_ONLY_MODULES={'agent_packaging','in_place_packaging','packaging_readiness'}
# Exact policy data required by the already-reviewed SDK ssl.py. This retains
# its emSign distrust policy; alternate CA stores or policy bytes are rejected.
SDK_TLS_POLICY_SHA256='c916ce1b14ed8ca69e9b5c9fab22799a900dd610d6d4ec9b1347f4fd48e53718'

def installed_executable(installation):
    """One canonical executable; support the authorized in-place brand migration."""
    installation=Path(installation)
    candidates=[installation/name for name in ('Offline Studio.exe','Offline GPT.exe') if (installation/name).is_file()]
    if len(candidates)!=1:raise ValueError('Expected exactly one main installed executable')
    return candidates[0]


def native_image_digest(data):
    """Exact PE image identity excluding only Authenticode bookkeeping.

    This is NOT a packaging hash exception. All deployed inputs still have to
    match installed raw SHA-256. It proves why current SDK signing variants may
    be used to analyse code while original installed bytes are explicitly pinned.
    """
    import pefile,struct
    pe=pefile.PE(data=data,fast_load=True)
    checksum=pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum')
    certificate=pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]
    directory=certificate.get_file_offset();offset,size=certificate.VirtualAddress,certificate.Size
    section_end=max([pe.OPTIONAL_HEADER.SizeOfHeaders]+[s.PointerToRawData+s.SizeOfRawData for s in pe.sections])
    if not (offset%8==0 and size>=8 and section_end<=offset and offset+size==len(data)):
        raise ValueError('Certificate overlay overlaps image, is unbounded or has trailing data')
    if not (checksum+4<=section_end and directory+8<=section_end):raise ValueError('Invalid PE signing metadata offsets')
    cursor=offset
    while cursor<offset+size:
        if cursor+8>offset+size:raise ValueError('Truncated WIN_CERTIFICATE')
        length,revision,kind=struct.unpack_from('<IHH',data,cursor)
        if length<8 or cursor+length>offset+size or revision!=0x200 or kind!=2:
            raise ValueError('Invalid WIN_CERTIFICATE entry')
        aligned=(length+7)&~7
        if cursor+aligned>offset+size or any(data[cursor+length:cursor+aligned]):raise ValueError('Invalid certificate alignment padding')
        cursor+=aligned
    normalized=bytearray(data[:offset])
    normalized[checksum:checksum+4]=bytes(4)
    normalized[directory:directory+8]=bytes(8)
    return hashlib.sha256(normalized).hexdigest()


def native_pin_inputs(approved,installation,compiled):
    """Recheck exact, independently reviewed SDK/installed signing-variant pairs."""
    if not isinstance(compiled,dict) or not compiled.get('nativeInputPinReceipt'):return []
    installation=Path(installation).absolute()
    def unredirected(path):
        path=Path(path).absolute()
        for part in [path,*path.parents]:
            if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Redirected native pin input')
        # Normalize lexical Windows components only after rejecting reparse
        # points. resolve() alone would hide the very junction we must reject.
        normalized=Path(os.path.abspath(path))
        for part in [normalized,*normalized.parents]:
            if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Redirected native pin input')
        return normalized
    path=unredirected(compiled['nativeInputPinReceipt'])
    if digest(path)!=compiled['nativeInputPinSha256']:raise ValueError('Native signing review changed')
    proof=json.loads(path.read_text(encoding='utf-8'))
    if proof.get('schemaVersion')!=1 or proof.get('status')!='PASS' or proof.get('purpose')!='PIN_INSTALLED_ORIGINALS_ONLY':raise ValueError('Unapproved native pin policy')
    if proof.get('installedExeSha256')!=compiled.get('exeSha256') or digest(installed_executable(installation))!=compiled.get('exeSha256'):raise ValueError('Native pins do not bind the current installed EXE')
    for authority in proof.get('authorityReceipts',[]):
        if digest(unredirected(authority['path']))!=authority['sha256']:raise ValueError('Independent native review authority changed')
    if not proof.get('authorityReceipts'):raise ValueError('Independent native review authority missing')
    pairs=proof.get('pairs')
    if not isinstance(pairs,list) or not 1<=len(pairs)<=64:raise ValueError('Invalid native pin count')
    relocations={}
    if compiled.get('originalInputRelocationReceipt'):
        relocation_path=unredirected(compiled['originalInputRelocationReceipt'])
        if digest(relocation_path)!=compiled.get('originalInputRelocationSha256'):raise ValueError('Original relocation receipt changed')
        relocation=json.loads(relocation_path.read_text(encoding='utf-8'))
        if (relocation.get('purpose')!='OWNER_APPROVED_EXACT_ORIGINAL_RELOCATION' or relocation.get('installedExeSha256')!=compiled['exeSha256'] or
            not relocation.get('ownerApproval') or relocation.get('historicalProofSha256')!=approved.get('nativeInputPins',{}).get('sha256')):raise ValueError('Original relocation approval mismatch')
        for item in relocation.get('entries',[]):
            key=item['destination'].casefold()
            if key in relocations:raise ValueError('Duplicate original relocation')
            relocations[key]=item
        if set(relocations)!={p['destination'].casefold() for p in pairs}:raise ValueError('Original relocation scope differs')
    prior={};seen=set();result=[]
    for row in approved['entries']:
        name=row['name'].replace('\\','/').casefold()
        if name in prior:raise ValueError('Duplicate prior native destination')
        prior[name]=row
    repeat_lineage=None
    def reviewed_repeat_lineage():
        # A prior successful Analysis has already pinned its origins to the
        # installation. Only its exact hash-bound former SDK origin can be
        # reused; a same-byte alias or a newly signed variant is not authority.
        nonlocal repeat_lineage
        if repeat_lineage is not None:return repeat_lineage
        lineage=approved.get('nativeInputPins')
        if approved.get('status')!='PASS' or not isinstance(lineage,dict):raise ValueError('Native repeat-pin lineage missing')
        historical_path=unredirected(lineage['receipt']);historical_sha=lineage['sha256']
        if digest(historical_path)!=historical_sha:raise ValueError('Native repeat-pin lineage receipt changed')
        if not any(unredirected(a['path'])==historical_path and a['sha256']==historical_sha for a in proof['authorityReceipts']):
            raise ValueError('Native repeat-pin lineage is not a fresh proof authority')
        historical=json.loads(historical_path.read_text(encoding='utf-8'))
        if (historical.get('schemaVersion')!=1 or historical.get('status')!='PASS' or
            historical.get('purpose')!='PIN_INSTALLED_ORIGINALS_ONLY' or
            historical.get('installedExeSha256')!=approved.get('installedExeSha256')):
            raise ValueError('Native repeat-pin lineage baseline differs')
        authorities=historical.get('authorityReceipts')
        if not isinstance(authorities,list) or not 1<=len(authorities)<=64:raise ValueError('Native repeat-pin lineage authorities missing')
        for authority in authorities:
            if digest(unredirected(authority['path']))!=authority['sha256']:raise ValueError('Native repeat-pin lineage authority changed')
        historical_pairs=historical.get('pairs');entries=lineage.get('entries')
        if not isinstance(historical_pairs,list) or not isinstance(entries,list) or not 1<=len(entries)<=64 or len(historical_pairs)!=len(entries):
            raise ValueError('Native repeat-pin lineage entries missing')
        previous={};records={}
        for item in historical_pairs:
            key=item['destination'].replace('\\','/').casefold()
            if key in previous:raise ValueError('Native repeat-pin lineage pair collision')
            previous[key]=item
        for item in entries:
            key=item['name'].replace('\\','/').casefold()
            if key in records:raise ValueError('Native repeat-pin lineage destination collision')
            records[key]=item
        if set(previous)!=set(records) or set(previous)!={p['destination'].replace('\\','/').casefold() for p in pairs}:
            raise ValueError('Native repeat-pin lineage destination set changed')
        immutable=('destination','kind','buildInput','buildSha256','installedInput','installedSha256',
                   'normalizedImageSha256','installedAuthenticode','buildAuthenticode')
        signer_corrections=None
        def reviewed_signer_metadata(old,item):
            # An owner-reviewed correction is a new authority, never a rewrite
            # of a historical declaration or an allowance for different bytes.
            nonlocal signer_corrections
            if signer_corrections is None:
                receipt=unredirected(compiled.get('signerMetadataCorrectionReceipt',''))
                if not receipt.is_file() or digest(receipt)!=compiled.get('signerMetadataCorrectionSha256'):
                    raise ValueError('Native repeat-pin lineage signer correction review changed or missing')
                review=json.loads(receipt.read_text(encoding='utf-8'))
                if (review.get('purpose')!='OWNER_APPROVED_EXACT_SIGNER_METADATA_CORRECTION' or
                    review.get('reviewStatus')!='OWNER_APPROVED' or not review.get('ownerApproval') or
                    review.get('installedExeSha256')!=compiled.get('exeSha256') or
                    review.get('historicalProofSha256')!=historical_sha or
                    review.get('correctedProofSha256')!=compiled.get('nativeInputPinSha256')):
                    raise ValueError('Native signer correction is not approved for this exact release')
                signer_corrections={}
                for entry in review.get('corrections',[]):
                    key=entry['originalPair']['destination'].replace('\\','/').casefold()
                    if key in signer_corrections:raise ValueError('Duplicate native signer correction')
                    signer_corrections[key]=entry
                if set(signer_corrections)!=set(previous):raise ValueError('Native signer correction scope differs')
            key=old['destination'].replace('\\','/').casefold()
            entry=signer_corrections[key]
            if entry.get('originalPair')!=old or entry.get('correctedPair')!=item:
                raise ValueError('Native signer correction differs from the exact reviewed pair')
            for field in ('installedAuthenticode','buildAuthenticode'):
                before=old[field];after=item[field]
                if (any(before.get(k)!=after.get(k) for k in ('Path','Status','Subject')) or
                    after.get('Status')!='Valid' or not after.get('Thumbprint')):
                    raise ValueError('Native signer correction changed publisher, status or path')
            # verify_build_environment additionally compares the declarations
            # against fresh Windows Authenticode observations for all 50 files.

        historical_relocations=None
        def approved_historical_relocations():
            """Recover the actual prior build's hash-bound owner authorization.

            A new relocation claim cannot explain an old Analysis origin. The
            old environment, compiled binding and approval must remain intact.
            """
            nonlocal historical_relocations
            if historical_relocations is not None:return historical_relocations
            env_path=unredirected(compiled.get('historicalBuildEnvironmentReceipt',''))
            env_sha=compiled.get('historicalBuildEnvironmentSha256')
            if not env_path.is_file() or digest(env_path)!=env_sha:
                raise ValueError('Native repeat-pin lineage historical environment changed or missing')
            if not any(unredirected(a['path'])==env_path and a['sha256']==env_sha for a in proof['authorityReceipts']):
                raise ValueError('Native repeat-pin lineage historical environment is not reviewed authority')
            env=json.loads(env_path.read_text(encoding='utf-8'))
            binding_path=unredirected(env['priorCompiledReceipt'])
            compatibility_path=unredirected(env['priorCompatibilityReceipt'])
            if (digest(binding_path)!=env['priorCompiledSha256'] or
                digest(compatibility_path)!=env['priorCompatibilitySha256']):
                raise ValueError('Native repeat-pin lineage historical build binding changed')
            binding=json.loads(binding_path.read_text(encoding='utf-8'))
            compatibility=json.loads(compatibility_path.read_text(encoding='utf-8'))
            if (binding.get('exeSha256')!=historical['installedExeSha256'] or
                binding.get('nativeInputPinSha256')!=historical_sha or
                unredirected(binding.get('nativeInputPinReceipt',''))!=historical_path or
                compatibility.get('status')!='PASS'):
                raise ValueError('Native repeat-pin lineage historical build identity differs')
            approval_path=unredirected(binding.get('originalInputRelocationReceipt',''))
            if not approval_path.is_file() or digest(approval_path)!=binding.get('originalInputRelocationSha256'):
                raise ValueError('Native repeat-pin lineage historical relocation approval changed')
            approval=json.loads(approval_path.read_text(encoding='utf-8'))
            if (approval.get('purpose')!='OWNER_APPROVED_EXACT_ORIGINAL_RELOCATION' or
                not approval.get('ownerApproval') or approval.get('installedExeSha256')!=historical['installedExeSha256'] or
                approval.get('historicalProofSha256')!=compatibility.get('nativeInputPins',{}).get('sha256')):
                raise ValueError('Native repeat-pin lineage historical relocation is not authorized')
            mapping={}
            for entry in approval.get('entries',[]):
                key=entry['destination'].casefold()
                if key in mapping:raise ValueError('Native repeat-pin lineage historical relocation collision')
                mapping[key]=entry
            if set(mapping)!=set(previous):raise ValueError('Native repeat-pin lineage historical relocation scope differs')
            historical_relocations=mapping
            return mapping
        for item in pairs:
            key=item['destination'].replace('\\','/').casefold();old=previous[key];record=records[key]
            if any(item.get(k)!=old.get(k) for k in immutable if k not in {'installedAuthenticode','buildAuthenticode'}):raise ValueError('Native repeat-pin lineage pair identity changed')
            if any(item.get(k)!=old.get(k) for k in ('installedAuthenticode','buildAuthenticode')):
                reviewed_signer_metadata(old,item)
            allowed_origins={unredirected(old['buildInput']),unredirected(old['installedInput'])}
            analysis_origin=unredirected(record['analysisInput'])
            if analysis_origin not in allowed_origins:
                authorized=approved_historical_relocations()[key]
                current=relocations.get(key)
                if (current!=authorized or unredirected(authorized['originalInput'])!=unredirected(old['buildInput']) or
                    authorized['sha256']!=old['buildSha256'] or
                    authorized['authenticode']!=dict(old['buildAuthenticode'],Path=authorized['recoveredInput'])):
                    raise ValueError('Native repeat-pin lineage historical relocation mapping differs')
                allowed_origins.add(unredirected(authorized['recoveredInput']))
            if (unredirected(record['pinnedInput'])!=unredirected(old['installedInput']) or
                record['installedSha256']!=old['installedSha256'] or analysis_origin not in allowed_origins or
                ('discoveredInput' in record and unredirected(record['discoveredInput']) not in allowed_origins)):
                raise ValueError('Native repeat-pin lineage origin changed')
        repeat_lineage=previous
        return previous
    for pair in pairs:
        name=pair['destination'].replace('\\','/');key=name.casefold()
        if key in seen or '/' in name or not key.endswith(('.dll','.pyd')):raise ValueError('Duplicate or invalid native pin destination')
        seen.add(key);row=prior.get(key)
        if not row or row['kind'] not in {'BINARY','EXTENSION'} or pair['kind']!=row['kind']:raise ValueError('Native pin outside prior approved inputs')
        source=unredirected(pair['buildInput']);target=unredirected(safe_destination(installation,name))
        if target!=unredirected(pair['installedInput']):raise ValueError('Native pin origin/path changed')
        if source!=unredirected(row['input']):
            if unredirected(row['input'])!=target:raise ValueError('Native pin origin/path changed')
            previous=reviewed_repeat_lineage()[key]
            if source!=unredirected(previous['buildInput']) or pair['kind']!=previous['kind']:
                raise ValueError('Native repeat-pin lineage build origin changed')
        original_source=source
        relocation=relocations.get(key)
        if relocation:
            if relocation.get('originalInput')!=str(source) or relocation.get('sha256')!=pair['buildSha256']:raise ValueError('Original relocation identity differs')
            source=unredirected(relocation['recoveredInput'])
            expected_signature=dict(pair['buildAuthenticode'],Path=str(source))
            if relocation.get('authenticode')!=expected_signature:raise ValueError('Original relocation signer differs')
        if pair['installedSha256']!=row['inputSha256'] or digest(target)!=pair['installedSha256'] or digest(source)!=pair['buildSha256']:raise ValueError('Native pin raw identity changed')
        signatures=[pair.get('installedAuthenticode',{}),pair.get('buildAuthenticode',{})]
        if any(s.get('Status')!='Valid' or not s.get('Subject') or not s.get('Thumbprint') for s in signatures) or signatures[0]['Subject']!=signatures[1]['Subject']:raise ValueError('Native signing identity is not independently verified')
        if signatures[0].get('Path')!=str(target) or signatures[1].get('Path')!=str(original_source):raise ValueError('Authenticode proof path changed')
        expected=pair['normalizedImageSha256']
        if native_image_digest(target.read_bytes())!=expected or native_image_digest(source.read_bytes())!=expected:raise ValueError('Native executable image changed beyond signing metadata')
        result.append(dict(pair,buildInput=str(source),**({'historicalBuildInput':str(original_source)} if relocation else {})))
    return result


def pin_analysis_native_inputs(analysis,installation,environment_receipt):
    """Select existing original installed bytes before exact Analysis validation."""
    record=json.loads(Path(environment_receipt).read_text(encoding='utf-8'))
    verify_build_environment(environment_receipt,installation)
    approved=json.loads(Path(record['priorCompatibilityReceipt']).read_text(encoding='utf-8'))
    compiled=json.loads(Path(record['priorCompiledReceipt']).read_text(encoding='utf-8')) if record.get('priorCompiledReceipt') else None
    pins=native_pin_inputs(approved,installation,compiled)
    if not pins:return []
    by_name={p['destination'].casefold():p for p in pins};observed=set();rebound=[]
    binaries=[]
    for name,source,kind in analysis.binaries:
        key=name.replace('\\','/').casefold();pair=by_name.get(key)
        if pair is None:binaries.append((name,source,kind));continue
        if key in observed or kind!=pair['kind']:raise ValueError('Duplicate or changed Analysis native pin kind')
        observed.add(key);actual=Path(source).absolute()
        discovered=actual
        if pair.get('historicalBuildInput') and actual==Path(pair['historicalBuildInput']).absolute():
            # Select the owner-approved exact originals. Discovered SDK variants
            # are not accepted as payload inputs or recorded as approved bytes.
            actual=Path(pair['buildInput']).absolute()
        if actual==Path(pair['buildInput']).absolute():expected=pair['buildSha256']
        elif actual==Path(pair['installedInput']).absolute():expected=pair['installedSha256']
        else:raise ValueError('Unexpected Analysis native origin: '+name)
        if digest(actual)!=expected:raise ValueError('Analysis native input changed: '+name)
        binaries.append((name,pair['installedInput'],kind))
        rebound.append({'name':name,'analysisInput':str(actual),'discoveredInput':str(discovered),'pinnedInput':pair['installedInput'],'installedSha256':pair['installedSha256']})
    if observed!=set(by_name):raise ValueError('Reviewed native pin missing from actual Analysis')
    analysis.binaries=binaries
    analysis._offlinegpt_native_pins={'receipt':compiled['nativeInputPinReceipt'],'sha256':compiled['nativeInputPinSha256'],'entries':rebound}
    return rebound


def controlled_build_environment(approved,installation,interpreter,base,system_root,parent,compiled=None):
    """Use retained Python/CRT origins, never the caller's native-tool PATH.

    This selects search directories before Analysis, not replacement binaries.
    The existing complete Analysis/compiled checks remain authoritative.
    """
    installation=Path(installation);base=Path(base);interpreter=Path(interpreter)
    current=digest(installed_executable(installation))
    # Analysis describes the *previous* installed EXE; its compiled receipt
    # binds the accepted resulting EXE. Preserve both identities, never relabel
    # the historical Analysis receipt as describing its later output.
    bound_output=(isinstance(compiled,dict) and compiled.get('exeSha256')==current
                  and 'app' in compiled.get('compiledCanonicalModules',[])
                  and 'app' in compiled.get('compiledScripts',[]))
    if approved.get('status')!='PASS' or not (approved.get('installedExeSha256')==current or bound_output):
        raise ValueError('A matching prior PASS dependency receipt is required')
    native_pins={p['destination'].casefold():p for p in native_pin_inputs(approved,installation,compiled)}
    selected={};crt_dirs=set()
    for row in approved['entries']:
        name=row['name'].replace('\\','/').casefold()
        if '/' in name:continue
        if name not in {'libssl-3-x64.dll','libcrypto-3-x64.dll','ucrtbase.dll'} and not name.startswith('api-ms-win-'):continue
        if name in selected:raise ValueError('Duplicate native search identity: '+name)
        source=Path(row['input']);target=safe_destination(installation,row['name'])
        pin=native_pins.get(name)
        # A repeated Analysis records the pinned installed payload as its input.
        # Search still uses only the exact independently verified former SDK
        # origin; do not put the application's DLL directory onto build PATH.
        if pin:source=Path(pin['buildInput'])
        actual=digest(source)
        if digest(target)!=row['inputSha256'] or (actual!=row['inputSha256'] and (not pin or actual!=pin['buildSha256'])):
            raise ValueError('Retained native search input changed: '+name)
        selected[name]={'name':row['name'],'input':str(source),'sha256':actual}
        if pin:selected[name]['installedSha256']=pin['installedSha256']
        if name.startswith('api-ms-win-') or name=='ucrtbase.dll':crt_dirs.add(source.parent.resolve())
        elif source.parent.resolve()!=(base/'DLLs').resolve() and not (pin and pin.get('historicalBuildInput') and Path(pin['historicalBuildInput']).parent.resolve()==(base/'DLLs').resolve()):raise ValueError('OpenSSL is not from the retained Python runtime')
    if not {'libssl-3-x64.dll','libcrypto-3-x64.dll','ucrtbase.dll'}<=set(selected) or len(crt_dirs)!=1:
        raise ValueError('Ambiguous or incomplete retained Python/CRT origins')
    relocation_roots=sorted({str(Path(p['buildInput']).parent) for p in native_pins.values() if p.get('historicalBuildInput')})
    roots=[*map(Path,relocation_roots),base/'DLLs',base,interpreter.parent,next(iter(crt_dirs)),Path(system_root)/'System32',Path(system_root)]
    paths=[]
    for root in roots:
        if not root.is_absolute() or not root.is_dir():raise ValueError('Missing native search directory: '+str(root))
        for part in [root,*root.parents]:
            if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('Redirected native search directory')
        if str(root) not in paths:paths.append(str(root))
    # Fail before invoking a builder if the directory ordering is ambiguous.
    for name,row in selected.items():
        found=next((Path(p)/row['name'] for p in paths if (Path(p)/row['name']).is_file()),None)
        if found is None or digest(found)!=row['sha256']:raise ValueError('Native search collision: '+name)
    env=dict(parent);env['PATH']=os.pathsep.join(paths)
    return env,{'path':env['PATH'],'pins':list(selected.values()),'installedExeSha256':current,'inputReceiptBaseExeSha256':approved['installedExeSha256'],'policy':'retained Python DLLs, prior exact CRT origin and Windows only; process-local'}

def _authenticode_signatures(paths):
    """Fresh Windows trust observations, isolated from PowerShell 7 module paths."""
    import base64,subprocess
    payload=base64.b64encode(json.dumps(paths).encode('utf-8')).decode('ascii')
    command=("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
             "$paths=ConvertFrom-Json ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+payload+"')));"
             "@($paths | ForEach-Object {$s=Get-AuthenticodeSignature -FilePath $_;"
             "[pscustomobject]@{Path=$_;Status=[string]$s.Status;Subject=$s.SignerCertificate.Subject;Thumbprint=$s.SignerCertificate.Thumbprint}}) | ConvertTo-Json -Depth 4")
    root=Path(os.environ.get('SystemRoot',r'C:\Windows'))
    shell=root/'System32/WindowsPowerShell/v1.0/powershell.exe'
    env=dict(os.environ,PSModulePath=str(root/'System32/WindowsPowerShell/v1.0/Modules'))
    result=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',command],
                          env=env,capture_output=True,text=True,encoding='utf-8',timeout=90,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
    return json.loads(result.stdout)


def verify_native_signatures(pairs,reader=None):
    """A historical declaration never substitutes for the file's actual signer."""
    expected={}
    for pair in pairs:
        for origin,checksum,signature in [('buildInput','buildSha256','buildAuthenticode'),('installedInput','installedSha256','installedAuthenticode')]:
            path=str(Path(pair[origin]).absolute());row=dict(pair[signature],Path=path,sha256=pair[checksum])
            if path in expected and expected[path]!=row:raise ValueError('Conflicting native signer observations')
            if digest(path)!=row['sha256']:raise ValueError('Native raw hash changed before signature verification: '+path)
            expected[path]=row
    if not expected:return []
    observations=(reader or _authenticode_signatures)(sorted(expected))
    actual={}
    for row in observations:
        if row.get('Path') in actual:raise ValueError('Duplicate actual native signature observation')
        actual[row.get('Path')]=row
    if set(actual)!=set(expected):raise ValueError('Actual native signature scope differs')
    for path,record in expected.items():
        row=actual[path]
        if row.get('Status')!='Valid' or any(row.get(k)!=record.get(k) for k in ('Status','Subject','Thumbprint')):
            raise ValueError('Actual native signer differs from reviewed declaration: '+path)
        if digest(path)!=record['sha256']:raise ValueError('Native raw hash changed during signature verification: '+path)
    return observations


def verify_build_environment(receipt,installation):
    """Pin the real build subprocess environment before Analysis can run."""
    record=json.loads(Path(receipt).read_text(encoding='utf-8'))
    prior=Path(record['priorCompatibilityReceipt'])
    if digest(prior)!=record['priorCompatibilitySha256']:raise ValueError('Prior dependency authority changed')
    approved=json.loads(prior.read_text(encoding='utf-8'))
    compiled=None
    if record.get('priorCompiledReceipt'):
        path=Path(record['priorCompiledReceipt'])
        if digest(path)!=record['priorCompiledSha256']:raise ValueError('Prior compiled authority changed')
        compiled=json.loads(path.read_text(encoding='utf-8'))
    env,expected=controlled_build_environment(approved,installation,record['interpreter'],record['basePrefix'],record['systemRoot'],{},compiled)
    if expected!=record['environment'] or os.environ.get('PATH')!=env['PATH']:
        raise ValueError('Actual build environment differs from its reviewed native search policy')
    verify_native_signatures(native_pin_inputs(approved,installation,compiled))
    return expected

def manifest_inputs(canonical):
    canonical=Path(canonical).resolve();entries={}
    for line in (canonical/'SOURCE_MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):continue
        checksum,name=line.split('  ',1)
        if len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):raise ValueError('Invalid source checksum')
        target=safe_destination(canonical,name)
        if name in entries or not target.is_file() or digest(target)!=checksum:raise ValueError('Source manifest mismatch: '+name)
        entries[name]=checksum
    validate_windows_payload_paths(list(entries))
    if 'app.py' not in entries:raise ValueError('Application entry missing from manifest')
    return entries

def runtime_modules(canonical,entries=None):
    entries=manifest_inputs(canonical) if entries is None else entries
    return {Path(n).stem:Path(canonical)/n for n in entries if '/' not in n and n.endswith('.py') and Path(n).stem not in BUILD_ONLY_MODULES|{'app'}}

def validate_build_locations(canonical,distpath,workpath,specname):
    """Pin actual PyInstaller globals, not only an example command line."""
    canonical=Path(canonical).absolute();root=canonical.parent
    if canonical.name!='Source' or specname!='Offline GPT.inplace':raise ValueError('Unexpected canonical spec identity')
    recovery=Path(os.environ.get('OFFLINEGPT_RELEASE_ROOT',str(root/'Recovery/VoiceRepair20261026'))).absolute()
    if recovery.is_symlink() or getattr(recovery,'is_junction',lambda:False)():raise ValueError('Redirected release root')
    expected_work=recovery/'Offline GPT.inplace'
    if canonical.is_symlink() or getattr(canonical,'is_junction',lambda:False)():raise ValueError('Redirected canonical source')
    for supplied,expected in [(Path(distpath).absolute(),recovery),(Path(workpath).absolute(),expected_work)]:
        if supplied!=expected:raise ValueError('Build output/work path is not the approved transient location: '+str(supplied)+' != '+str(expected))
        for p in [supplied,*supplied.parents]:
            if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('Redirected build path')
            if p==root:break
        if supplied.exists() and not supplied.is_dir():raise ValueError('Build directory is a file')
    if expected_work.exists() and any(expected_work.iterdir()):raise ValueError('Stale build work must be reviewed before this one build')
    cache=recovery/'Offline GPT.inplace-import-cache'
    if cache.exists():raise ValueError('Import cache must be fresh, not reused')
    for receipt in ['PACKAGING_COMPATIBILITY.json','COMPILED_SOURCE_ACCEPTANCE.json']:
        if (recovery/receipt).exists():raise ValueError('Fresh release evidence already exists: '+receipt)
    # exclude_binaries=True places EXE in workpath in this retained PyInstaller.
    # The owner-approved v6 receipt independently records this exact location.
    output=expected_work/'Offline Studio.exe'
    if any((directory/name).exists() for directory in (expected_work,recovery) for name in ('Offline Studio.exe','Offline GPT.exe')):raise ValueError('Transient executable already exists; do not overwrite evidence')
    return {'distpath':str(recovery),'workpath':str(expected_work),'output':str(output)}

def load_module_code(path):
    path=Path(path)
    if path.suffix=='.py':return compile(path.read_bytes(),str(path),'exec',dont_inherit=True,optimize=0)
    if path.suffix=='.pyc':
        import importlib.util
        data=path.read_bytes()
        if data[:4]!=importlib.util.MAGIC_NUMBER:raise ValueError('Incompatible Python bytecode')
        return marshal.loads(data[16:])
    raise ValueError('Unsupported Python module input: '+str(path))

def safe_destination(root,name):
    name=windows_payload_path(str(name))
    if ':' in name or name.startswith('/') or any(x in {'','..','.'} for x in name.split('/')):
        raise ValueError('Unsafe packaged destination: '+name)
    root=Path(root).resolve();p=root/name
    if not p.resolve().is_relative_to(root):raise ValueError('Dependency escapes the installation: '+name)
    if any(x.is_symlink() or getattr(x,'is_junction',lambda:False)() for x in [p,*p.parents] if x!=root and x.is_relative_to(root)):
        raise ValueError('Redirected installed dependency: '+name)
    return p

def compare_base_zip(installed,fresh):
    with zipfile.ZipFile(installed) as a,zipfile.ZipFile(fresh) as b:
        validate_windows_payload_paths(a.namelist());validate_windows_payload_paths(b.namelist())
        if any(not n.endswith('.pyc') for n in a.namelist()+b.namelist()):raise ValueError('Unexpected frozen base-library member')
        aa=set(a.namelist());bb=set(b.namelist())
        if aa!=bb:raise ValueError('Frozen base-library module set changed')
        for name in aa:
            left=a.read(name);right=b.read(name)
            if left[:4]!=right[:4] or code_identity(marshal.loads(left[16:]))!=code_identity(marshal.loads(right[16:])):
                raise ValueError('Incompatible frozen standard-library module: '+name)
    return len(aa)

def validate_analysis(analysis,installation,canonical,receipt):
    """Compare every collected input with its retained installed counterpart."""
    from PyInstaller.archive.readers import CArchiveReader
    installation=Path(installation).resolve();canonical=Path(canonical).resolve()
    approved=manifest_inputs(canonical);required=runtime_modules(canonical,approved)
    evidence={'sourceManifestSha256':digest(canonical/'SOURCE_MANIFEST.sha256'),'canonicalSource':approved,'status':'FAIL','installedExeSha256':digest(installed_executable(installation)),'entries':[],'pure':[],'scripts':[],'errors':[]}
    try:
        old_archive=CArchiveReader(str(installed_executable(installation)));old=old_archive.open_embedded_archive('PYZ.pyz')
        validate_windows_payload_paths([str(e[0]) for e in list(analysis.binaries)+list(analysis.datas)])
        required_assets={n.casefold():n for n in approved if n.startswith('ui/') or n in {'assistant_system_prompt.md','codex-rejected-cas.pem'}}
        destinations=set()
        for name,source,kind in list(analysis.binaries)+list(analysis.datas):
            target=safe_destination(installation,name);key=str(name).replace('\\','/').casefold()
            if key in destinations:raise ValueError('Colliding packaging destination: '+str(name))
            destinations.add(key);source=Path(source)
            if not source.is_file():raise ValueError('Missing packaging input: '+str(source))
            changed_ui=key.startswith('ui/') and source.resolve().is_relative_to(canonical/'ui')
            row={'name':str(name),'input':str(source.resolve()),'inputSha256':digest(source),'installedSha256':digest(target) if target.is_file() else None,'kind':kind}
            if key=='base_library.zip':row['semanticModules']=compare_base_zip(target,source)
            elif changed_ui or key in {'assistant_system_prompt.md','codex-rejected-cas.pem'}:
                if key not in required_assets or source.resolve()!=(canonical/required_assets[key]).resolve() or row['inputSha256']!=approved[required_assets[key]]:raise ValueError('Noncanonical or swapped application asset: '+str(name))
                if key=='codex-rejected-cas.pem' and row['inputSha256']!=SDK_TLS_POLICY_SHA256:raise ValueError('SDK TLS distrust policy bytes changed')
                row['applicationAsset']=True
            else:
                if not target.is_file() or digest(target)!=row['inputSha256']:
                    raise ValueError('Installed dependency absent or different: '+str(name))
            evidence['entries'].append(row)
        missing_assets=sorted(set(required_assets)-destinations)
        if missing_assets:raise ValueError('Missing frontend/application assets: '+', '.join(missing_assets))
        script_names=set()
        for name,source,kind in analysis.scripts:
            if name in script_names:raise ValueError('Duplicate executable script: '+name)
            script_names.add(name);source=Path(source)
            if name=='app':
                if source.resolve()!=(canonical/'app.py').resolve():raise ValueError('Shadowed application entry')
            elif name not in old_archive.toc or code_identity(marshal.loads(old_archive.extract(name)))!=code_identity(load_module_code(source)):
                raise ValueError('Unreviewed executable runtime hook: '+name)
            evidence['scripts'].append({'module':name,'input':str(source.resolve()),'inputSha256':digest(source)})
        if 'app' not in script_names:raise ValueError('Application entry script missing')
        observed={}
        for name,source,kind in analysis.pure:
            if name in observed:raise ValueError('Duplicate Python module: '+name)
            if source in (None,'-'):
                if name in required:raise ValueError('Canonical module cannot be a namespace: '+name)
                if name not in old.toc or old.extract(name) is not None:raise ValueError('Unverified namespace module: '+name)
                observed[name]=None;evidence['pure'].append({'module':name,'namespace':True});continue
            source=Path(source);app_source=source.resolve().is_relative_to(canonical)
            if name in required and source.resolve()!=required[name].resolve():raise ValueError('Shadowed canonical module: '+name)
            if app_source:
                if name not in required or source.resolve()!=required[name].resolve():raise ValueError('Unapproved canonical module: '+name)
            else:
                if name in old.toc:
                    original_code=old.extract(name)
                elif name=='struct' and name in old_archive.toc:
                    # PyInstaller keeps its bootstrap 'struct' in the executable CArchive,
                    # rather than PYZ or base_library.zip. No general exception is allowed.
                    if old_archive.toc[name][-1]!='m':
                        raise ValueError('Unexpected installed bootstrap struct entry type')
                    original_code=marshal.loads(old_archive.extract(name))
                else:
                    raise ValueError('New unreviewed frozen dependency: '+name)
                if code_identity(original_code)!=code_identity(load_module_code(source)):
                    raise ValueError('Frozen dependency source changed: '+name)
            observed[name]=str(source.resolve())
            evidence['pure'].append({'module':name,'input':str(source.resolve()),'inputSha256':digest(source),'canonical':app_source})
        missing=sorted(set(required)-set(observed))
        if missing:raise ValueError('Missing canonical modules: '+', '.join(missing))
        evidence['status']='PASS'
    except Exception as exc:evidence['errors'].append(str(exc));raise
    finally:
        if getattr(analysis,'_offlinegpt_native_pins',None):evidence['nativeInputPins']=analysis._offlinegpt_native_pins
        receipt=Path(receipt);receipt.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence

def verify_compiled_application(exe,analysis,canonical,compatibility_receipt):
    from PyInstaller.archive.readers import CArchiveReader
    canonical=Path(canonical).resolve()
    evidence=json.loads(Path(compatibility_receipt).read_text(encoding='utf-8'))
    if evidence.get('status')!='PASS' or evidence['sourceManifestSha256']!=digest(canonical/'SOURCE_MANIFEST.sha256') or evidence['canonicalSource']!=manifest_inputs(canonical):raise ValueError('Source changed during packaging')
    for row in evidence['entries']+evidence['pure']+evidence['scripts']:
        if row.get('input') and digest(row['input'])!=row['inputSha256']:raise ValueError('Packaging input changed: '+row.get('module',row.get('name','unknown')))
    for row in evidence['entries']:
        target=safe_destination(canonical.parent/'Application',row['name'])
        if (digest(target) if target.is_file() else None)!=row['installedSha256']:raise ValueError('Installed dependency/asset changed during packaging: '+row['name'])
    if digest(installed_executable(canonical.parent/'Application'))!=evidence['installedExeSha256']:raise ValueError('Installed EXE changed during packaging')
    archive=CArchiveReader(str(exe));pyz=archive.open_embedded_archive('PYZ.pyz');checked=[]
    dependency_count=0
    for name,source,kind in analysis.pure:
        if name in pyz.toc:embedded=pyz.extract(name)
        elif name in archive.toc:embedded=marshal.loads(archive.extract(name))
        else:raise ValueError('Compiled module missing: '+name)
        if source in (None,'-'):
            if embedded is not None:raise ValueError('Compiled namespace differs: '+name)
            continue
        source=Path(source);fresh=load_module_code(source)
        if code_identity(embedded)!=code_identity(fresh):raise ValueError('Compiled dependency/source differs: '+name)
        if source.resolve().is_relative_to(canonical):checked.append(name)
        else:dependency_count+=1
    for name,source,kind in analysis.scripts:
        if code_identity(marshal.loads(archive.extract(name)))!=code_identity(load_module_code(source)):
            raise ValueError('Compiled executable script differs: '+name)
    # Entry script lives in the executable CArchive, outside PYZ.
    source=canonical/'app.py';code=marshal.loads(archive.extract('app'))
    if code_identity(code)!=code_identity(compile(source.read_bytes(),str(source),'exec',dont_inherit=True,optimize=0)):
        raise ValueError('Compiled app entry differs')
    checked.append('app');return {'exeSha256':digest(exe),'compiledCanonicalModules':checked,'compiledDependencyModules':dependency_count,'compiledScripts':[r[0] for r in analysis.scripts]}
