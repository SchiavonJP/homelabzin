import argparse
import json
from sqlmodel import Session

from app.config import Settings
from app.db import initialize, make_engine
from app.main import overview
from app.services import enqueue
from app.worker import tick


def main():
    parser = argparse.ArgumentParser(prog="xereta")
    parser.add_argument("command", choices=["init", "status", "run", "tick", "openapi", "set-password"])
    args = parser.parse_args()
    cfg = Settings()
    if args.command == "openapi":
        from app.main import create_app
        print(json.dumps(create_app(cfg).openapi(), ensure_ascii=False))
        return
    engine = make_engine(cfg.database_url)
    initialize(engine, cfg)
    if args.command == "set-password":
        from getpass import getpass
        from app.models import User
        from app.security import get_password_hash
        from sqlmodel import select
        password = getpass("Nova senha (mínimo 14 caracteres): ")
        if len(password) < 14 or password != getpass("Repita a senha: "):
            raise SystemExit("Senha curta ou confirmação diferente")
        with Session(engine) as s:
            user = s.exec(select(User).where(User.email == cfg.owner_email)).one()
            user.password_hash = get_password_hash(password)
            s.add(user)
            s.commit()
        print("password_updated")
    elif args.command == "run":
        from uuid import uuid4
        with Session(engine) as s:
            print(enqueue(s, "cli:" + str(uuid4())).model_dump_json())
    elif args.command == "tick":
        tick(engine, cfg)
    else:
        print(json.dumps(overview(engine, cfg), ensure_ascii=False))


if __name__ == "__main__":
    main()
