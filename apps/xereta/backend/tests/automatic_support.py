"""Synthetic, persistent remote state for automatic worker process deaths."""
import multiprocessing as mp
import httpx
from app.config import Settings
from app.db import make_engine
from app.memory import Memory, validate_review
from app.vault import Vault
from recovery_support import Backend, WorkerProcess


def child_tick(payload, armed, pipe):
    from app import automatic_worker, worker
    cfg=Settings(**payload); backend=Backend(cfg.state_path)
    def stop(point, value=''):
        if point==armed:
            pipe.send({'point':point,'value':value});pipe.recv()
    automatic_worker.Vault=lambda settings:Vault(settings,httpx.MockTransport(lambda req:backend.vault(req,stop)))
    automatic_worker.Memory=lambda settings:Memory(settings,httpx.MockTransport(lambda req:backend.memory(req,stop)))
    def synthetic(settings,sources,versions,trusted):
        backend.audit('DRAFT','synthetic')
        return validate_review({'items':[{'issue':'automatic-recovery','kind':'finding','text':'Synthetic original statement.',
            'reason':'Test only.','evidence':[{'source_id':sources[0].id,'quote':versions[sources[0].id].body[:30]}]}]},sources,versions,trusted)
    automatic_worker.draft=synthetic
    original=automatic_worker.store_review
    def store(*args):stop('draft-saved');return original(*args)
    automatic_worker.store_review=store
    engine=make_engine(cfg.database_url)
    try:worker.tick(engine,cfg)
    finally:engine.dispose();pipe.close()


class AutomaticProcess(WorkerProcess):
    def __init__(self,settings,armed=''):
        ctx=mp.get_context('spawn');self.pipe,child=ctx.Pipe()
        self.process=ctx.Process(target=child_tick,args=(settings.model_dump(),armed,child))
        self.process.start();child.close()
