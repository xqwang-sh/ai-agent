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
        self.model_receipts=[];self.reference_receipts=[];self.errors=[];self.task_dir=None
        owner=self
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
                    response={'id':item['id'],'object':'chat.completion','model':body.get('model','synthetic'),
                              'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(item['response'],ensure_ascii=False)},'finish_reason':'stop'}],
                              'usage':item['usage']}
                    projection={}
                    if owner.task_dir is not None:
                        for name in ('state','proof'):
                            path=owner.task_dir/(name+'.json')
                            if path.is_file():projection[name]=json.loads(path.read_text())
                    owner.model_receipts.append({'script_id':item['id'],'expected_stage':item['stage'],'request':body,'response':response,'projection':projection})
                    if item.get('delay_seconds'):time.sleep(item['delay_seconds'])
                    self.reply(200,response)
                elif self.path=='/reference':
                    i=len(owner.reference_receipts)
                    if i>=len(owner.references):
                        owner.errors.append('unexpected extra reference request');self.reply(409,{'error':'reference script exhausted'});return
                    response=income_envelope(owner.references[i]);owner.reference_receipts.append({'request':body,'response':response});self.reply(200,response)
                else:
                    owner.errors.append('unexpected endpoint '+self.path);self.reply(404,{'error':'unexpected endpoint'})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.server.shutdown();self.server.server_close();self.thread.join()

def run_with_services(subject, scenario, output, after_create=None, wait_timeout_seconds=None):
    with ScriptedServices(scenario) as services:
        base='http://127.0.0.1:'+str(services.server.server_port)
        request={k:deepcopy(v) for k,v in scenario.items() if k not in ('model_script','reference_script','pages')}
        request.update(model_endpoint=base+'/v1/chat/completions',reference_endpoint=base+'/reference',synthetic=True)
        def created(task_dir):
            services.task_dir=Path(task_dir)
            if after_create is not None:after_create(task_dir)
        kwargs={'after_create':created}
        if wait_timeout_seconds is not None:kwargs['wait_timeout_seconds']=wait_timeout_seconds
        result=subject.run(request,output,**kwargs)
        receipts={'model_receipts':services.model_receipts,'reference_receipts':services.reference_receipts,'errors':services.errors}
        if services.errors:raise AssertionError(services.errors)
        return result,receipts
