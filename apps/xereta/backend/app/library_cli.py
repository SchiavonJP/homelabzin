"""Operator JSON configuration interface; uses the same schemas and guards as the UI."""
import argparse
import json
from pathlib import Path
from sqlmodel import Session
from app.config import Settings
from app.db import make_engine
from app.library_api import ConfigFile,ImportConfig,router,validated
from app.library_config import export_configuration


def main():
    parser=argparse.ArgumentParser(prog='xereta-library')
    parser.add_argument('command',choices=['export','preview','apply'])
    parser.add_argument('--file',type=Path)
    parser.add_argument('--library-revision',type=int,default=0)
    parser.add_argument('--automation-revision',type=int,default=0)
    parser.add_argument('--affine-revision',type=int,default=0)
    args=parser.parse_args();settings=Settings();engine=make_engine(settings.database_url)
    if args.command=='export':
        with Session(engine) as s:
            value=export_configuration(s)
            if value['affine']:value['affine']={k:value['affine'][k] for k in ('workspace','exclusions')}
            print(json.dumps(value,ensure_ascii=False,indent=2))
        return
    if not args.file or args.file.stat().st_size>1024*1024:raise SystemExit('valid_configuration_file_required')
    document=ConfigFile.model_validate_json(args.file.read_bytes());value=validated(document,settings)
    if args.command=='preview':print(json.dumps({'document':value,'ingestion_will_be_paused':True},ensure_ascii=False,indent=2));return
    # Reuse exactly the application handler; CLI execution requires server/operator access.
    routes=router(engine,settings,lambda:None,lambda:None)
    handler=next(r.endpoint for r in routes.routes if r.path.endswith('/connections/import'))
    result=handler(ImportConfig(document=document,expected_revision=args.library_revision,
        expected_automation_revision=args.automation_revision,expected_affine_revision=args.affine_revision))
    print(json.dumps(result))


if __name__=='__main__':main()
