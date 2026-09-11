#!/usr/bin/env python3
"""Auditable company work queue and employee status ledger.

The queue is objective-agnostic. Company roles decide what work means; this
tool only provides durable add, claim, progress, complete, requeue, and status
transitions shared by every employee.
"""
import argparse
import datetime
import json
import os
import pathlib
import pwd
import sqlite3
import sys


ROOT = pathlib.Path(os.environ.get("ATTOSYS_ROOT", pathlib.Path(__file__).resolve().parent))
DB_PATH = pathlib.Path(os.environ.get("ATTOSYS_WORKQUEUE", ROOT / "shared" / "workqueue.sqlite3"))
STATES = ("queued", "claimed", "completed")
WORKER_STATES = ("working", "blocked", "idle")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def actor():
    return pwd.getpwuid(os.geteuid()).pw_name


def company():
    path = ROOT / "company.yaml"
    if not path.is_file():
        return {}
    import yaml
    loaded = yaml.safe_load(path.read_text())
    return loaded if isinstance(loaded, dict) else {}


def capabilities(name):
    configured = company()
    org = configured.get("org")
    if not org or not name.startswith(f"{org}-"):
        return set()
    role = name.removeprefix(f"{org}-")
    spec = (configured.get("agents") or {}).get(role) or {}
    return {role, spec.get("soul", role)}


def configured_workers():
    configured = company()
    org = configured.get("org")
    agents = configured.get("agents") or {}
    names = {f"{org}-{role}" for role in agents} if org else set()
    roles = set(agents)
    roles.update(spec.get("soul", role) for role, spec in agents.items())
    return names, roles


def connect(path=None):
    path = DB_PATH if path is None else pathlib.Path(path)
    old_umask = os.umask(0o007)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS items(
          id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          title TEXT NOT NULL,
          details TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT '',
          priority INTEGER NOT NULL DEFAULT 0,
          required_role TEXT,
          assignee TEXT,
          state TEXT NOT NULL CHECK(state IN ('queued','claimed','completed')),
          claimed_by TEXT,
          claimed_at TEXT,
          result TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS items_ready
          ON items(state, priority DESC, created_at, id);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY,
          item_id INTEGER,
          created_at TEXT NOT NULL,
          actor TEXT NOT NULL,
          event TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',
          FOREIGN KEY(item_id) REFERENCES items(id)
        );
        CREATE TABLE IF NOT EXISTS worker_status(
          actor TEXT PRIMARY KEY,
          updated_at TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('working','blocked','idle')),
          summary TEXT NOT NULL,
          item_id INTEGER,
          FOREIGN KEY(item_id) REFERENCES items(id)
        );
        """)
        os.chmod(path, 0o660)
        return db
    finally:
        os.umask(old_umask)


def initialize(root=ROOT, gid=None):
    """Create the queue during provisioning and give the company group access."""
    path = pathlib.Path(root) / "shared" / "workqueue.sqlite3"
    db = connect(path)
    db.close()
    if gid is not None:
        os.chown(path, 0, gid)
    os.chmod(path, 0o660)


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def add(args):
    timestamp = now()
    who = actor()
    names, roles = configured_workers()
    if args.role and roles and args.role not in roles:
        raise ValueError(f"unknown required role or soul: {args.role}")
    if args.assignee and names and args.assignee not in names:
        raise ValueError(f"unknown assignee: {args.assignee}")
    with connect() as db:
        cursor = db.execute(
            """INSERT INTO items(created_at,updated_at,title,details,source,priority,
                                  required_role,assignee,state)
               VALUES(?,?,?,?,?,?,?,?, 'queued')""",
            (timestamp, timestamp, args.title, args.details, args.source,
             args.priority, args.role, args.assignee),
        )
        item_id = cursor.lastrowid
        db.execute("INSERT INTO events(item_id,created_at,actor,event,note) VALUES(?,?,?,?,?)",
                   (item_id, timestamp, who, "created", args.details))
    emit({"id": item_id, "state": "queued"})


def eligible(row, who):
    if row["assignee"] and row["assignee"] != who:
        return False
    return not row["required_role"] or row["required_role"] in capabilities(who)


def claim(args):
    who = actor()
    timestamp = now()
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        if args.id is not None:
            row = db.execute("SELECT * FROM items WHERE id=?", (args.id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown work item: {args.id}")
            candidates = [row]
        else:
            candidates = db.execute(
                "SELECT * FROM items WHERE state='queued' ORDER BY priority DESC,created_at,id"
            ).fetchall()
        row = next((candidate for candidate in candidates
                    if candidate["state"] == "queued" and eligible(candidate, who)), None)
        if row is None:
            raise ValueError("no eligible queued work item")
        db.execute("""UPDATE items SET state='claimed',claimed_by=?,claimed_at=?,updated_at=?
                      WHERE id=? AND state='queued'""", (who, timestamp, timestamp, row["id"]))
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise ValueError("work item was claimed concurrently")
        db.execute("INSERT INTO events(item_id,created_at,actor,event,note) VALUES(?,?,?,?,?)",
                   (row["id"], timestamp, who, "claimed", ""))
        db.execute("COMMIT")
        claimed = db.execute("SELECT * FROM items WHERE id=?", (row["id"],)).fetchone()
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()
    emit(dict(claimed))


def owned_item(db, item_id, who):
    row = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown work item: {item_id}")
    if row["state"] != "claimed" or row["claimed_by"] != who:
        raise ValueError(f"work item {item_id} is not claimed by {who}")
    return row


def progress(args):
    who = actor()
    timestamp = now()
    with connect() as db:
        owned_item(db, args.id, who)
        db.execute("UPDATE items SET updated_at=? WHERE id=?", (timestamp, args.id))
        db.execute("INSERT INTO events(item_id,created_at,actor,event,note) VALUES(?,?,?,?,?)",
                   (args.id, timestamp, who, "progress", args.note))
        db.execute("""INSERT INTO worker_status(actor,updated_at,state,summary,item_id)
                      VALUES(?,?,?,?,?) ON CONFLICT(actor) DO UPDATE SET
                      updated_at=excluded.updated_at,state=excluded.state,
                      summary=excluded.summary,item_id=excluded.item_id""",
                   (who, timestamp, "working", args.note, args.id))
    emit({"id": args.id, "state": "claimed", "updated_at": timestamp})


def complete(args):
    who = actor()
    timestamp = now()
    with connect() as db:
        owned_item(db, args.id, who)
        db.execute("""UPDATE items SET state='completed',result=?,updated_at=? WHERE id=?""",
                   (args.evidence, timestamp, args.id))
        db.execute("INSERT INTO events(item_id,created_at,actor,event,note) VALUES(?,?,?,?,?)",
                   (args.id, timestamp, who, "completed", args.evidence))
        db.execute("""INSERT INTO worker_status(actor,updated_at,state,summary,item_id)
                      VALUES(?,?,?,?,NULL) ON CONFLICT(actor) DO UPDATE SET
                      updated_at=excluded.updated_at,state=excluded.state,
                      summary=excluded.summary,item_id=NULL""",
                   (who, timestamp, "working", f"completed work item {args.id}; selecting next work"))
    emit({"id": args.id, "state": "completed"})


def requeue(args):
    who = actor()
    timestamp = now()
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM items WHERE id=?", (args.id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown work item: {args.id}")
        if row["state"] == "completed":
            raise ValueError("completed work cannot be requeued")
        if row["state"] == "claimed" and row["claimed_by"] != who and os.geteuid() != 0:
            raise ValueError(f"work item {args.id} is claimed by {row['claimed_by']}")
        db.execute("""UPDATE items SET state='queued',claimed_by=NULL,claimed_at=NULL,
                      updated_at=? WHERE id=?""", (timestamp, args.id))
        db.execute("INSERT INTO events(item_id,created_at,actor,event,note) VALUES(?,?,?,?,?)",
                   (args.id, timestamp, who, "requeued", args.reason))
        db.execute("COMMIT")
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()
    emit({"id": args.id, "state": "queued"})


def report(args):
    who = actor()
    timestamp = now()
    with connect() as db:
        if args.item is not None:
            owned_item(db, args.item, who)
        db.execute("""INSERT INTO worker_status(actor,updated_at,state,summary,item_id)
                      VALUES(?,?,?,?,?) ON CONFLICT(actor) DO UPDATE SET
                      updated_at=excluded.updated_at,state=excluded.state,
                      summary=excluded.summary,item_id=excluded.item_id""",
                   (who, timestamp, args.state, args.summary, args.item))
        db.execute("INSERT INTO events(item_id,created_at,actor,event,note) VALUES(?,?,?,?,?)",
                   (args.item, timestamp, who, f"status:{args.state}", args.summary))
    emit({"actor": who, "state": args.state, "updated_at": timestamp})


def list_items(args):
    with connect() as db:
        query = "SELECT * FROM items"
        values = []
        conditions = []
        if args.state:
            conditions.append("state=?")
            values.append(args.state)
        if args.claimed_by:
            conditions.append("claimed_by=?")
            values.append(args.claimed_by)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY CASE state WHEN 'claimed' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, priority DESC, updated_at DESC"
        rows = [dict(row) for row in db.execute(query, values)]
    emit(rows)


def history(args):
    with connect() as db:
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM events WHERE item_id=? ORDER BY id", (args.id,))]
    emit(rows)


def dashboard(args):
    with connect() as db:
        counts = {state: db.execute("SELECT count(*) FROM items WHERE state=?", (state,)).fetchone()[0]
                  for state in STATES}
        recorded = {row["actor"]: dict(row) for row in db.execute(
            "SELECT * FROM worker_status ORDER BY actor")}
        active = [dict(row) for row in db.execute(
            "SELECT id,title,priority,required_role,assignee,claimed_by,updated_at FROM items WHERE state!='completed' ORDER BY state,priority DESC,created_at")]
    names, _ = configured_workers()
    workers = []
    current = datetime.datetime.now(datetime.timezone.utc)
    for name in sorted(names | set(recorded)):
        status = recorded.get(name, {"actor": name, "updated_at": None, "state": "missing",
                                     "summary": "no status reported", "item_id": None})
        if status["updated_at"]:
            updated = datetime.datetime.fromisoformat(status["updated_at"])
            status["age_hours"] = round((current - updated).total_seconds() / 3600, 2)
        else:
            status["age_hours"] = None
        workers.append(status)
    emit({"counts": counts, "workers": workers, "active_items": active})


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    command = commands.add_parser("add", help="create a queued work item")
    command.add_argument("--title", required=True)
    command.add_argument("--details", default="")
    command.add_argument("--source", default="")
    command.add_argument("--priority", type=int, default=0)
    command.add_argument("--role", help="required company role or soul")
    command.add_argument("--assignee", help="exact employee name")
    command.set_defaults(function=add)

    command = commands.add_parser("claim", help="atomically claim eligible work")
    command.add_argument("id", type=int, nargs="?")
    command.set_defaults(function=claim)

    command = commands.add_parser("progress", help="record progress on claimed work")
    command.add_argument("id", type=int)
    command.add_argument("--note", required=True)
    command.set_defaults(function=progress)

    command = commands.add_parser("complete", help="complete claimed work")
    command.add_argument("id", type=int)
    command.add_argument("--evidence", required=True)
    command.set_defaults(function=complete)

    command = commands.add_parser("requeue", help="release claimed or queued work")
    command.add_argument("id", type=int)
    command.add_argument("--reason", required=True)
    command.set_defaults(function=requeue)

    command = commands.add_parser("report", help="publish current employee status")
    command.add_argument("--state", choices=WORKER_STATES, required=True)
    command.add_argument("--summary", required=True)
    command.add_argument("--item", type=int)
    command.set_defaults(function=report)

    command = commands.add_parser("list", help="list work items as JSON")
    command.add_argument("--state", choices=STATES)
    command.add_argument("--claimed-by")
    command.set_defaults(function=list_items)

    command = commands.add_parser("history", help="show a work item's audit trail")
    command.add_argument("id", type=int)
    command.set_defaults(function=history)

    command = commands.add_parser("dashboard", help="show queue and employee status")
    command.set_defaults(function=dashboard)
    return result


def main():
    args = parser().parse_args()
    try:
        args.function(args)
    except (OSError, sqlite3.Error, ValueError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
