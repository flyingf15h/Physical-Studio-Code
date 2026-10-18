# Ported from circuit-studio/builder.py at 21a4f23: the model pool (Gemini 3.8 on every key, hedged, then
# gpt-6.1-sol). Changes: keys come from the environment only, and the OpenAI fallback uses the openai SDK.
import base64, os, re, threading, time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from google import genai
from google.genai import types

# ---- Model pool: Gemini 3.8 on every key, then OpenAI -------------------------------------------
# Each request starts on the next Gemini key in turn. Out of quota/credits (429) -> next key; a
# rejected key (401/403/invalid) is skipped for an hour; overloaded (500/503/504/timeout) -> OpenAI,
# and Gemini is skipped for 10 minutes. Hedging: if Gemini hasn't answered after HEDGE_S seconds,
# the same request also goes to OpenAI and the first answer wins (gemini-3.8-flash on Oct 17
# answered pings but hung real requests). Older Gemini models are left out on purpose: their
# breadboard placements were too inaccurate. Add any with STUDIO_FALLBACK_MODELS if wanted.
RealClient=genai.Client
OPENAI='openai:'+os.environ.get('OPENAI_STUDIO_MODEL',os.environ.get('OPENAI_DESIGN_MODEL','gpt-6.1-sol'))
FALLBACK_MODELS=[m.strip() for m in os.environ.get('STUDIO_FALLBACK_MODELS','').split(',') if m.strip()]+([OPENAI] if os.environ.get('OPENAI_API_KEY') else [])
TIMEOUT_MS=int(os.environ.get('STUDIO_GEMINI_TIMEOUT_MS','120000'))
OPENAI_TIMEOUT_S=float(os.environ.get('STUDIO_OPENAI_TIMEOUT_S','240'))
HEDGE_S=float(os.environ.get('STUDIO_GEMINI_HEDGE_S','45'))
POOL={'turn':0,'key_cool':{},'model_cool':{}};LOCK=threading.Lock()
WORKERS=ThreadPoolExecutor(max_workers=16,thread_name_prefix='gemini')

def load_keys():
    """The Build helper's own keys first (STUDIO_GEMINI_API_KEYS), then the team's (GEMINI_API_KEYS, GEMINI_API_KEY)."""
    keys=[*os.environ.get('STUDIO_GEMINI_API_KEYS','').split(','),*os.environ.get('GEMINI_API_KEYS','').split(','),os.environ.get('GEMINI_API_KEY','')]
    return list(dict.fromkeys(k.strip() for k in keys if k.strip()))
KEYS=load_keys()
print(f'[bench] {len(KEYS)} Gemini key(s) in the pool',flush=True)

def classify(e):
    code=getattr(e,'code',None);text=f'{type(e).__name__} {e}'
    if code==429 or re.search(r'RESOURCE_EXHAUSTED|quota|credit|billing',text,re.I):return 'quota'
    if code in (401,403) or re.search(r'API_KEY_INVALID|API key (not valid|expired)|PERMISSION_DENIED|UNAUTHENTICATED',text,re.I):return 'bad_key'
    if code==404:return 'no_model'
    if code in (500,502,503,504) or re.search(r'UNAVAILABLE|DEADLINE_EXCEEDED|overloaded|high demand|Timeout|timed out',text,re.I):return 'busy'
    return 'other'

def hide(text):
    for k in KEYS+[os.environ.get('OPENAI_API_KEY','')]:
        if k:text=text.replace(k,'[key]')
    return text

class ModelFailed(Exception):pass

class OpenAIAnswer:
    def __init__(self,text):self.text=text

def try_openai(model,contents,config,tried):
    """Same request through OpenAI's Responses API (the openai SDK mcp-server already uses)."""
    import openai
    parts=[]
    for c in contents if isinstance(contents,list) else [contents]:
        if isinstance(c,str):parts.append({'type':'input_text','text':c})
        elif getattr(c,'inline_data',None) is not None:
            parts.append({'type':'input_image','image_url':f"data:{c.inline_data.mime_type};base64,{base64.b64encode(c.inline_data.data).decode()}"})
        elif getattr(c,'text',None):parts.append({'type':'input_text','text':c.text})
    extra={}
    schema=getattr(config,'response_schema',None)
    if schema is not None:
        js=schema.model_json_schema() if hasattr(schema,'model_json_schema') else schema
        extra['text']={'format':{'type':'json_schema','name':'answer','schema':js,'strict':False}}
        parts.insert(0,{'type':'input_text','text':'Reply with JSON only, matching the given schema.'})
    client=openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'],timeout=OPENAI_TIMEOUT_S,max_retries=0)
    try:
        r=client.responses.create(model=model,input=[{'role':'user','content':parts}],reasoning={'effort':'medium'},**extra)
        text=r.output_text or ''
        if not text.strip():tried.append(f'openai/{model}: empty');raise ModelFailed('OpenAI returned no text.')
        return OpenAIAnswer(text)
    except openai.APIStatusError as e:
        kind={429:'used up',401:'rejected',403:'rejected'}.get(e.status_code,'overloaded' if e.status_code>=500 else 'error')
        tried.append(f'openai/{model}: {kind}');raise ModelFailed(hide(f'OpenAI {e.status_code}: {str(e)[:300]}'))
    except openai.APIError as e:
        tried.append(f'openai/{model}: overloaded');raise ModelFailed(hide(str(e))[:300])
    finally:client.close()

def try_model(m,contents,config,tried):
    """Every usable key on one model. Returns the response, or raises ModelFailed."""
    if m.startswith('openai:'):return try_openai(m[7:],contents,config,tried)
    if not KEYS:tried.append(f'{m}: no Gemini key');raise ModelFailed('')  # no keys configured: go straight to the next model
    now=time.time()
    with LOCK:start=POOL['turn']%len(KEYS);POOL['turn']+=1
    keys=KEYS[start:]+KEYS[:start];keys.sort(key=lambda k:max(POOL['key_cool'].get((k,m),0),POOL['key_cool'].get(k,0))>now)
    last=''
    for k in keys:
        client=RealClient(api_key=k,http_options=types.HttpOptions(timeout=TIMEOUT_MS))
        try:return client.models.generate_content(model=m,contents=contents,config=config)
        except Exception as e:
            kind=classify(e);last=hide(str(e))[:400]
            tried.append(f'{m}/key{KEYS.index(k)+1}: '+{'quota':'used up','bad_key':'rejected','busy':'overloaded','no_model':'unavailable'}.get(kind,'error'))
            if kind=='quota':POOL['key_cool'][(k,m)]=time.time()+60
            elif kind=='bad_key':POOL['key_cool'][k]=time.time()+3600
            elif kind=='busy':POOL['model_cool'][m]=time.time()+600;break
            else:break  # unavailable model or a request this model rejects: move on to the next model
        finally:client.close()
    raise ModelFailed(last)

def pooled_generate(contents,config=None,model=None):
    now=time.time();tried=[];errors=[]
    models=list(dict.fromkeys([model or os.environ.get('GEMINI_MODEL','gemini-3.8-flash'),*FALLBACK_MODELS]))
    models.sort(key=lambda m:POOL['model_cool'].get(m,0)>now)  # overloaded models go last
    queue=list(models);running={}
    def launch():
        m=queue.pop(0);running[WORKERS.submit(try_model,m,contents,config,tried)]=m
    launch()
    while running:
        done,_=wait(list(running),timeout=HEDGE_S,return_when=FIRST_COMPLETED)
        if not done:  # nobody answered in time: hedge on the next model, keep the slow one running
            if queue:launch()
            continue
        for f in done:
            m=running.pop(f)
            try:
                result=f.result()  # first answer wins; slower requests finish in the background
                for slow in running.values():POOL['model_cool'][slow]=max(POOL['model_cool'].get(slow,0),time.time()+300)  # beaten by a hedge: start elsewhere for 5 min
                return result
            except ModelFailed as e:
                if str(e):errors.append(str(e))
                if queue and len(running)<2:launch()
    detail=(' Last error: '+errors[-1][:300]) if errors else ''
    raise RuntimeError('Gemini and OpenAI are both busy right now. Wait a minute and try again. Tried: '+', '.join(tried)+'.'+detail.replace('quota','limit').replace('429','rate-limit'))

# app.py's prompt shows rail keys with a ROW placeholder; lighter fallback models copy it literally
# ("Unknown terminal rail_1_21.6_ROW"), so spell it out before sending and re-ask once if it leaks.
