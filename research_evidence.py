"""Conservative passage support checks, not a semantic entailment oracle."""
import re,unicodedata

STOP=set('a an the is are was were be been being of and or for to in on at by with as it its this that these those from has have had can will would should may according source says states'.split())
def normalized(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value)).casefold()).strip()
def words(value):return set(re.findall(r'[^\W\d_]+',normalized(value),re.UNICODE))-STOP
def numbers(value):
    return {re.sub(r'[,\s]','',v).casefold() for v in re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?:\s*(?:cc|bhp|nm|kg|mm|km/h|kw|%))?\b',str(value),re.I)}
def preceding_claim(text,offset):
    before=text[max(0,offset-700):offset]
    before=re.sub(r'\[K[a-f0-9]{16}\](?:\([^)]*\))?','',before)
    parts=re.split(r'(?<=[.!?])\s+|\n',before.strip())
    return (parts[-1] if parts else before).strip(' -*\t')
def check_support(claim,source):
    excerpt=str(source.get('excerpt',''));clean=normalized(excerpt);claim=claim.strip();claimed=words(claim);available=words(excerpt)
    quotes=re.findall(r'["“]([^"”]{12,})["”]',claim);missing_quotes=[q for q in quotes if normalized(q) not in clean]
    if len(claimed)<=1 and not numbers(claim) and not quotes:
        return {'claimText':claim,'sourceId':source['id'],'supportStatus':'CITATION_ONLY','reason':'No substantive claim text precedes the citation.','contentOverlap':0.0,'unmatchedNumbers':[],'automaticCheckScope':'literal quote/numbers/negation/content overlap; not perfect entailment','requiresReview':False}
    absent_numbers=numbers(claim)-numbers(excerpt);overlap=len(claimed&available)/max(1,len(claimed))
    negation=bool(re.search(r'\b(?:not|never|no|without)\b',normalized(claim))) and not re.search(r'\b(?:not|never|no|without)\b',clean)
    reason='';status='INTERPRETATION_REQUIRES_REVIEW'
    if missing_quotes:status='UNSUPPORTED';reason='Quoted text is absent from the cited evidence excerpt.'
    elif absent_numbers:status='DERIVATION_OR_UNSUPPORTED';reason='Claim contains numeric values absent from the cited passage; no verified derivation is recorded.'
    elif negation:status='UNSUPPORTED';reason='Negation is not supported by the cited passage.'
    elif overlap<.18:status='UNSUPPORTED';reason='Insufficient passage overlap for this claim.'
    elif quotes:status='DIRECT_QUOTE_MATCH';reason='Quoted text and stated numeric values occur in the passage.'
    elif overlap>=.5:status='PASSAGE_SUPPORT_CANDIDATE';reason='Content terms/numeric values overlap; independent semantic entailment is not certified.'
    return {'claimText':claim,'sourceId':source['id'],'supportStatus':status,'reason':reason,'contentOverlap':round(overlap,3),'unmatchedNumbers':sorted(absent_numbers),'automaticCheckScope':'literal quote/numbers/negation/content overlap; not perfect entailment','requiresReview':status not in {'DIRECT_QUOTE_MATCH','PASSAGE_SUPPORT_CANDIDATE'}}

def source_conflicts(sources):
    # Surface competing measurements with the same unit, without guessing which
    # subject or model year makes either source authoritative.
    units={}
    for source in sources:
        for value,unit in re.findall(r'\b(\d+(?:\.\d+)?)\s*(cc|bhp|kw|nm|kg)\b',source.get('excerpt',''),re.I):
            units.setdefault(unit.casefold(),{}).setdefault(value,set()).add(source['id'])
    return [{'unit':unit,'values':[{'value':value,'sourceIds':sorted(ids)} for value,ids in values.items()],'status':'POTENTIAL_CONFLICT_CHECK_ENTITY_VARIANT_AND_DATE'} for unit,values in units.items() if len(values)>1]
