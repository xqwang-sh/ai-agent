"""Independent loopback transport owned by public acceptance, never the app."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from .fixtures import income_envelope

class ScriptedServices:
    def __init__(self, scenario):
        self.models=deepcopy(scenario['model_script']);self.references=deepcopy(scenario['reference_script'])
        self.model_receipts=[];self.reference_receipts=[];self.errors=[];self.task_dir=None;self.task_root=None
        self.reference_delay_seconds=scenario.get('reference_delay_seconds',0)
        owner=self
        def projection():
            directory=owner.task_dir
            if directory is None and owner.task_root is not None:
                root=Path(owner.task_root)
                directories=[path for path in root.iterdir()
                             if path.is_dir() and (path/'state.json').is_file()] if root.exists() else []
                if len(directories)==1:directory=directories[0]
            result={}
            if directory is not None:
                for key,filename in [('state','state.json'),('proof','proof.json'),('journal','stage-journal.json'),('trace','trace.json')]:
                    path=Path(directory)/filename
                    if path.is_file():result[key]=json.loads(path.read_text())
                versions=[]
                for event in result.get('trace',{}).get('external_evaluations',[]):
                    path=Path(event['reference_path'])
                    if path.is_file():
                        raw=path.read_bytes()
                        versions.append({'path':str(path),'sha256':__import__('hashlib').sha256(raw).hexdigest(),'content':json.loads(raw)})
                result['reference_versions']=versions
            return result
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,status,value):
                data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();
                try:self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_GET(self):self.handle_request()
            def do_POST(self):self.handle_request()
            def handle_request(self):
                n=int(self.headers.get('Content-Length','0'));body=json.loads(self.rfile.read(n) or b'{}')
                if self.path=='/v1/chat/completions':
                    i=len(owner.model_receipts)
                    if i>=len(owner.models):
                        owner.errors.append('unexpected extra model request');self.reply(409,{'error':'script exhausted'});return
                    item=owner.models[i]
                    content=item['raw_content'] if 'raw_content' in item else json.dumps(item['response'],ensure_ascii=False)
                    response={'id':item['id'],'object':'chat.completion','model':body.get('model','synthetic'),
                              'choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],
                              'usage':item['usage']}
                    owner.model_receipts.append({'script_id':item['id'],'expected_stage':item['stage'],'request':body,'response':response,'projection':projection()})
                    if item.get('delay_seconds'):time.sleep(item['delay_seconds'])
                    self.reply(200,response)
                elif self.path=='/reference':
                    i=len(owner.reference_receipts)
                    if i>=len(owner.references):
                        owner.errors.append('unexpected extra reference request');self.reply(409,{'error':'reference script exhausted'});return
                    response=income_envelope(owner.references[i]);owner.reference_receipts.append({'request':body,'response':response,'projection':projection()})
                    if owner.reference_delay_seconds:time.sleep(owner.reference_delay_seconds)
                    self.reply(200,response)
                else:
                    owner.errors.append('unexpected endpoint '+self.path);self.reply(404,{'error':'unexpected endpoint'})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.server.shutdown();self.server.server_close();self.thread.join()

def transport_request(scenario, services):
    base='http://127.0.0.1:'+str(services.server.server_port)
    request={k:deepcopy(v) for k,v in scenario.items() if k not in ('model_script','reference_script','pages','reference_delay_seconds')}
    request.update(model_endpoint=base+'/v1/chat/completions',synthetic=True)
    if request.get('reference_cli'):
        request.pop('reference_endpoint',None)
    else:
        request['reference_endpoint']=base+'/reference'
    return request

def run_with_services(subject, scenario, output, after_create=None, wait_timeout_seconds=None):
    with ScriptedServices(scenario) as services:
        request=transport_request(scenario,services)
        def created(task_dir):
            services.task_dir=Path(task_dir)
            if after_create is not None:after_create(task_dir)
        kwargs={'after_create':created}
        if wait_timeout_seconds is not None:kwargs['wait_timeout_seconds']=wait_timeout_seconds
        result=subject.run(request,output,**kwargs)
        receipts={'model_receipts':services.model_receipts,'reference_receipts':services.reference_receipts,'errors':services.errors}
        if services.errors:raise AssertionError(services.errors)
        return result,receipts
