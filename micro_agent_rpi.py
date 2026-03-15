#!/usr/bin/env python3
"""
SYNTDOCS Micro-Agent — Raspberry Pi
Footprint: ~8 MB RAM | ~2 MB storage
Target: Raspberry Pi 4/3/Zero 2W (ARM)

Install:
    pip install aiohttp aiofiles msgpack --no-deps
    python3 micro_agent_rpi.py --role parser --id RPI_001
"""
import asyncio
import json
import os
import gc
import sys
import aiohttp
import aiofiles
import msgpack  # 3x plus compact que JSON
from pathlib import Path
from dataclasses import dataclass


# Force la libération mémoire agressive (contrainte Pi Zero)
gc.enable()
gc.set_threshold(100, 5, 5)


@dataclass
class MicroConfig:
    """Configuration de l'agent micro embarqué."""
    agent_id: str
    role: str
    server_url: str = os.getenv("NEXUS_URL", "http://192.168.1.1:8000")
    poll_ms: int = 500
    max_payload: int = 64 * 1024  # 64 KB max (contrainte Pi Zero)


class RpiMicroAgent:
    """
    Agent Raspberry Pi — dépendances minimales, tourne sur tous les modèles Pi.
    Utilise HTTP polling au lieu de WebSocket pour économiser la mémoire.
    Supporte : parsing de documents, OCR, opérations fichiers locales.
    """

    def __init__(self, cfg: MicroConfig):
        self.cfg = cfg
        self.session: aiohttp.ClientSession = None
        # Table de dispatch des handlers par type de tâche
        self._handlers = {
            "parse_text":  self._handle_parse,
            "read_file":   self._handle_read,
            "write_file":  self._handle_write,
            "system_info": self._handle_sysinfo,
        }

    async def start(self):
        """Démarre l'agent et lance les boucles en parallèle."""
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        print(f"[{self.cfg.agent_id}] 🟢 Pi agent online")
        await asyncio.gather(
            self._poll_loop(),
            self._heartbeat_loop()
        )

    async def _poll_loop(self):
        """Boucle principale de polling des tâches depuis NEXUS."""
        url = f"{self.cfg.server_url}/agent/{self.cfg.agent_id}/task"
        while True:
            try:
                async with self.session.get(url) as r:
                    if r.status == 200:
                        # Décode msgpack (3x plus léger que JSON)
                        data = msgpack.unpackb(await r.read())
                        await self._dispatch(data)
            except Exception as e:
                print(f"[{self.cfg.agent_id}] Poll error: {e}", file=sys.stderr)
            finally:
                gc.collect()  # Libère la mémoire après chaque tâche
            await asyncio.sleep(self.cfg.poll_ms / 1000)

    async def _dispatch(self, task: dict):
        """Dispatch la tâche vers le handler approprié."""
        handler = self._handlers.get(task.get("type"))
        if not handler:
            return await self._report(task["id"], {"error": "unknown_type"})
        result = await handler(task["payload"])
        await self._report(task["id"], result)

    async def _handle_parse(self, payload: dict) -> dict:
        """
        Tokenisation légère — pas de spaCy sur Pi Zero.
        Extrait les mots-clés et compte les tokens.
        """
        text = payload.get("text", "")
        # Nettoyage et tokenisation simple sans librairie lourde
        words = [w.strip(".,!?;:\"'") for w in text.split()]
        unique = list(set(w.lower() for w in words if len(w) > 3))[:50]
        return {
            "word_count": len(words),
            "keywords":   unique[:20],
            "chars":      len(text)
        }

    async def _handle_read(self, payload: dict) -> dict:
        """Lit un fichier local de façon asynchrone."""
        path = Path(payload["path"])
        if not path.exists():
            return {"error": "file_not_found"}
        async with aiofiles.open(path, "r") as f:
            content = await f.read(self.cfg.max_payload)
        return {"content": content, "size": path.stat().st_size}

    async def _handle_write(self, payload: dict) -> dict:
        """Écrit un fichier local de façon asynchrone."""
        path = Path(payload["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "w") as f:
            await f.write(payload["content"])
        return {"written": len(payload["content"]), "path": str(path)}

    async def _handle_sysinfo(self, _) -> dict:
        """Retourne les infos système du Pi (RAM, CPU, Python)."""
        import resource
        mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {
            "platform":  "raspberry_pi",
            "mem_kb":    mem,
            "python":    sys.version.split()[0],
            "cpu_count": os.cpu_count(),
        }

    async def _report(self, task_id: str, result: dict):
        """Envoie le résultat au serveur NEXUS via msgpack."""
        url = f"{self.cfg.server_url}/result/{task_id}"
        data = msgpack.packb({"agent": self.cfg.agent_id, "result": result})
        try:
            async with self.session.post(url, data=data) as r:
                pass
        except Exception as e:
            print(f"Report failed: {e}", file=sys.stderr)

    async def _heartbeat_loop(self):
        """Envoie un heartbeat toutes les 10s pour signaler que l'agent est vivant."""
        while True:
            try:
                await self.session.post(
                    f"{self.cfg.server_url}/heartbeat",
                    json={"id": self.cfg.agent_id, "role": self.cfg.role}
                )
            except Exception:
                pass  # Silencieux — le heartbeat est non-critique
            await asyncio.sleep(10)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="SYNTDOCS Micro-Agent Raspberry Pi")
    p.add_argument("--id",   default="RPI_001", help="Identifiant unique de l'agent")
    p.add_argument("--role", default="parser",  help="Rôle : parser | relay | export")
    args = p.parse_args()

    cfg = MicroConfig(agent_id=args.id, role=args.role)
    asyncio.run(RpiMicroAgent(cfg).start())
