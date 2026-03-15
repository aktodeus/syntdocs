#!/usr/bin/env python3
"""
SYNTDOCS — Serveur NEXUS (Orchestrateur Central)
=================================================
Stack  : FastAPI + asyncio + msgpack
Lancer : python3 nexus_server.py
Docs   : http://localhost:8000/docs
"""
import asyncio, gc, json, os, sys, time, uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    import msgpack
    from fastapi import FastAPI, HTTPException, Request, UploadFile, File
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response
    import uvicorn
except ImportError:
    print("pip install fastapi uvicorn msgpack python-multipart aiofiles")
    sys.exit(1)

# ── Modèles ───────────────────────────────────────────────
@dataclass
class Agent:
    agent_id:   str
    role:       str
    platform:   str   = "unknown"
    last_seen:  float = field(default_factory=time.time)
    status:     str   = "idle"
    tasks_done: int   = 0

@dataclass
class Task:
    task_id:    str
    task_type:  str
    payload:    Dict[str, Any]
    agent_id:   Optional[str]  = None
    status:     str            = "pending"
    created_at: float          = field(default_factory=time.time)
    result:     Optional[Dict] = None

# ── État global ───────────────────────────────────────────
agents:       Dict[str, Agent] = {}
task_queues:  Dict[str, deque] = defaultdict(deque)
results:      Dict[str, Any]   = {}
task_history: deque            = deque(maxlen=1000)
metrics = {"tasks_total":0,"tasks_done":0,"tasks_error":0,
           "agents_online":0,"start_time":time.time()}

# ── App ───────────────────────────────────────────────────
app = FastAPI(title="SYNTDOCS NEXUS", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Routes agents ─────────────────────────────────────────
@app.post("/heartbeat")
async def heartbeat(data: dict):
    aid = data.get("id")
    if not aid:
        raise HTTPException(status_code=400, detail="Champ 'id' requis")
    if aid not in agents:
        agents[aid] = Agent(agent_id=aid, role=data.get("role","unknown"),
                            platform=data.get("hw","unknown"))
    else:
        agents[aid].last_seen = time.time()
        agents[aid].status    = "idle"
    metrics["agents_online"] = sum(1 for a in agents.values()
                                   if time.time()-a.last_seen < 30)
    return {"ok": True, "server_time": time.time()}

@app.get("/agent/{agent_id}/task")
async def get_task_for_agent(agent_id: str):
    # File dédiée puis file générale
    queue = task_queues.get(agent_id)
    if not queue:
        general = task_queues.get("*")
        if not general:
            return JSONResponse(status_code=204, content=None)
        task = general.popleft()
    else:
        task = queue.popleft()
    if agent_id in agents:
        agents[agent_id].status = "busy"
    task.agent_id = agent_id
    task.status   = "assigned"
    body = msgpack.packb({"id":task.task_id,"type":task.task_type,
                           "payload":task.payload}, use_bin_type=True)
    return Response(content=body, media_type="application/x-msgpack")

@app.post("/result/{task_id}")
async def receive_result(task_id: str, request: Request):
    # BUG FIX : signature correcte — lit le body via Request
    raw = await request.body()
    try:    data = msgpack.unpackb(raw, raw=False)
    except Exception:
        try:    data = json.loads(raw)
        except Exception: data = {}
    results[task_id] = {"done":True, "agent":data.get("agent","?"),
                        "result":data.get("result",{}), "received_at":time.time()}
    aid = data.get("agent")
    if aid and aid in agents:
        agents[aid].status     = "idle"
        agents[aid].tasks_done += 1
    metrics["tasks_done"] += 1
    if len(results) > 5000:
        for k in list(results.keys())[:1000]: del results[k]
        gc.collect()
    return {"ok": True}

# ── Routes client ─────────────────────────────────────────
@app.get("/status")
async def get_status():
    now = time.time()
    return {
        "nexus":"online", "uptime_s":int(now-metrics["start_time"]),
        "agents_online":metrics["agents_online"],
        "tasks_total":metrics["tasks_total"], "tasks_done":metrics["tasks_done"],
        "queue_size":sum(len(q) for q in task_queues.values()),
        "agents":[{
            "id":a.agent_id,"role":a.role,"platform":a.platform,
            "status":"online" if now-a.last_seen<30 else "offline",
            "tasks_done":a.tasks_done,"last_seen_s":int(now-a.last_seen)
        } for a in agents.values()],
    }

@app.post("/task/submit")
async def submit_task(data: dict):
    task = Task(task_id=str(uuid.uuid4()),
                task_type=data.get("type","parse_text"),
                payload=data.get("payload",{}))
    target    = data.get("agent")
    queue_key = target if (target and target in agents) else "*"
    task_queues[queue_key].append(task)
    task_history.append(task)
    metrics["tasks_total"] += 1
    return {"task_id":task.task_id,"status":"queued",
            "queue_key":queue_key,"created_at":task.created_at}

@app.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    if task_id in results:
        return {"status":"done","result":results[task_id]}
    for t in task_history:
        if t.task_id == task_id:
            return {"status":t.status,"result":t.result}
    raise HTTPException(status_code=404, detail=f"Tâche '{task_id}' introuvable")

@app.post("/document/process")
async def process_document(file: UploadFile = File(...)):
    sid    = str(uuid.uuid4())
    body   = await file.read()
    texte  = body.decode("utf-8", errors="replace")[:65536]
    t_l = Task(f"{sid}_lector","parse_text",
               {"text":texte,"filename":file.filename,"size":len(body)})
    t_c = Task(f"{sid}_cognos","parse_text",{"text":texte,"mode":"semantic"})
    lq = task_queues["LECTOR_01"] if "LECTOR_01" in agents else task_queues["*"]
    cq = task_queues["COGNOS_01"] if "COGNOS_01" in agents else task_queues["*"]
    lq.append(t_l); cq.append(t_c)
    task_history.append(t_l); task_history.append(t_c)
    metrics["tasks_total"] += 2
    return {"session_id":sid,"filename":file.filename,"size":len(body),
            "tasks":[t_l.task_id,t_c.task_id],"status":"processing"}

@app.get("/agents/list")
async def list_agents():
    now = time.time()
    return [{"id":a.agent_id,"role":a.role,"platform":a.platform,
             "online":now-a.last_seen<30,"status":a.status}
            for a in agents.values()]

@app.delete("/agents/{agent_id}")
async def deregister_agent(agent_id: str):
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent introuvable")
    del agents[agent_id]
    task_queues.pop(agent_id, None)
    metrics["agents_online"] = max(0, metrics["agents_online"]-1)
    return {"ok":True,"removed":agent_id}

# ── Startup & nettoyage ───────────────────────────────────
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_cleanup_loop())
    print("╔══════════════════════════════════╗")
    print("║   SYNTDOCS NEXUS  v1.0  ✓        ║")
    print("║   http://0.0.0.0:8000            ║")
    print("║   Docs : /docs                   ║")
    print("╚══════════════════════════════════╝")

async def _cleanup_loop():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for a in agents.values():
            if now - a.last_seen > 30: a.status = "offline"
        for k in [k for k,v in results.items()
                  if isinstance(v,dict) and now-v.get("received_at",now)>3600]:
            del results[k]
        gc.collect()

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host",   default="0.0.0.0")
    p.add_argument("--port",   default=8000, type=int)
    p.add_argument("--reload", action="store_true")
    a = p.parse_args()
    uvicorn.run("nexus_server:app", host=a.host, port=a.port,
                reload=a.reload, log_level="info")
