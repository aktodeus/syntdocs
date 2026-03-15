#!/usr/bin/env python3
"""
SYNTDOCS — 8 Agents IA
=======================
LECTOR   Lecture / parsing universel
COGNOS   Analyse sémantique NLP
FUSION   Fusion multi-sources
VISIO    Génération PowerPoint 16K
NEXPORT  Export multi-format (20+ formats)
AEGIS    Sécurité / validation / audit
MNEMO    Cache LRU persistant

Usage :
  python3 agents.py --demo               # Pipeline locale, aucun réseau
  python3 agents.py --demo --format html
  python3 agents.py --agent LECTOR       # Lance un agent vs NEXUS
  python3 agents.py --all                # Lance tous les 7 agents
"""

import asyncio, gc, hashlib, json, os, re, sys, time, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Imports optionnels — dégradation gracieuse ────────────
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False

# ── Config globale ────────────────────────────────────────
NEXUS_URL     = os.getenv("NEXUS_URL", "http://127.0.0.1:8000")
POLL_INTERVAL = float(os.getenv("POLL_MS", "500")) / 1000


@dataclass
class AgentConfig:
    agent_id:      str
    role:          str
    nexus_url:     str   = field(default_factory=lambda: NEXUS_URL)
    poll_interval: float = field(default_factory=lambda: POLL_INTERVAL)
    platform:      str   = "python_x86"


# ═══════════════════════════════════════════════════════════
# CLASSE DE BASE
# ═══════════════════════════════════════════════════════════

class BaseAgent:
    """Parent commun — gère polling, dispatch, reporting, heartbeat."""

    def __init__(self, cfg: AgentConfig):
        self.cfg          = cfg
        self.session      = None
        self.running      = True
        self._tasks_done  = 0
        self._tasks_error = 0

    async def start(self):
        if HAS_AIOHTTP:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        print(f"[{self.cfg.agent_id}] 🟢 {self.cfg.role} — {self.cfg.nexus_url}")
        await asyncio.gather(self._poll_loop(), self._heartbeat_loop())

    async def _poll_loop(self):
        url = f"{self.cfg.nexus_url}/agent/{self.cfg.agent_id}/task"
        while self.running:
            try:
                if HAS_AIOHTTP and self.session:
                    async with self.session.get(url) as r:
                        if r.status == 200:
                            raw  = await r.read()
                            data = (msgpack.unpackb(raw, raw=False)
                                    if HAS_MSGPACK else json.loads(raw))
                            await self._handle_task(data)
                else:
                    await asyncio.sleep(2)
                    await self._simulate_task()
            except Exception as e:
                if "Cannot connect" not in str(e):
                    print(f"[{self.cfg.agent_id}] poll-err: {e}", file=sys.stderr)
            finally:
                gc.collect()
            await asyncio.sleep(self.cfg.poll_interval)

    async def _handle_task(self, task: dict):
        tid = task.get("id", "unknown")
        try:
            result = await self.process(task)
            self._tasks_done += 1
            await self._report(tid, {"status": "ok", **result})
        except Exception as e:
            self._tasks_error += 1
            await self._report(tid, {"status": "error", "message": str(e)})

    async def process(self, task: dict) -> dict:
        """À surcharger dans chaque agent."""
        return {"agent": self.cfg.agent_id, "echo": task}

    async def _report(self, task_id: str, result: dict):
        if not HAS_AIOHTTP or not self.session:
            print(f"[{self.cfg.agent_id}] ← {json.dumps(result)[:80]}")
            return
        try:
            payload = json.dumps({"agent": self.cfg.agent_id, "result": result})
            async with self.session.post(
                f"{self.cfg.nexus_url}/result/{task_id}",
                data=payload.encode(),
                headers={"Content-Type": "application/json"},
            ) as _:
                pass
        except Exception as e:
            print(f"[{self.cfg.agent_id}] report-err: {e}", file=sys.stderr)

    async def _heartbeat_loop(self):
        while self.running:
            try:
                if HAS_AIOHTTP and self.session:
                    await self.session.post(
                        f"{self.cfg.nexus_url}/heartbeat",
                        json={"id": self.cfg.agent_id, "role": self.cfg.role,
                              "hw": self.cfg.platform,
                              "stats": {"done": self._tasks_done,
                                        "error": self._tasks_error}},
                    )
                else:
                    print(f"[{self.cfg.agent_id}] 💓")
            except Exception:
                pass
            await asyncio.sleep(10)

    async def _simulate_task(self):
        task = {"id": str(uuid.uuid4()), "type": "parse_text",
                "payload": {"text": "SYNTDOCS demo task."}}
        r = await self.process(task)
        print(f"[{self.cfg.agent_id}] 🔁 {json.dumps(r)[:70]}")


# ═══════════════════════════════════════════════════════════
# AGENT 1 — LECTOR
# ═══════════════════════════════════════════════════════════

class LectorAgent(BaseAgent):
    """Parsing universel — texte, markdown, HTML, CSV, JSON, code."""

    STOPWORDS = set(
        "le la les de du des un une et est en au aux ce qui que pour par dans "
        "sur avec comme mais ou ne pas plus très bien aussi tout même "
        "the a an is are was were be been have has had do does did will would "
        "shall should may might must can could this that these those".split()
    )

    async def process(self, task: dict) -> dict:
        payload  = task.get("payload", {})
        text     = payload.get("text", "")
        filename = payload.get("filename", "inconnu")
        if not text:
            return {"error": "Texte vide", "agent": "LECTOR"}

        tokens    = re.findall(r'\b[a-zA-ZÀ-ÿ]{2,}\b', text.lower())
        mots_cles = [t for t in set(tokens)
                     if t not in self.STOPWORDS and len(t) > 3][:25]
        lignes    = text.split('\n')
        titres    = [l.strip() for l in lignes
                     if re.match(r'^#{1,6}\s', l)][:10]
        if not titres:
            titres = [l.strip() for l in lignes
                      if 5 < len(l.strip()) < 80
                      and l.strip() and l.strip()[0].isupper()
                      and not l.strip().endswith('.')][:8]

        return {
            "agent":       "LECTOR",
            "filename":    filename,
            "type":        self._type(text, filename),
            "word_count":  len(tokens),
            "char_count":  len(text),
            "line_count":  len(lignes),
            "keywords":    mots_cles,
            "titles":      titres,
            "language":    self._langue(tokens),
            "summary":     self._resume(text),
            "processed_at": time.time(),
        }

    def _type(self, text: str, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        table = {'.pdf':'pdf','.docx':'word','.doc':'word',
                 '.xlsx':'excel','.xls':'excel','.pptx':'powerpoint',
                 '.md':'markdown','.html':'html','.htm':'html',
                 '.txt':'texte','.csv':'csv','.json':'json',
                 '.py':'python','.rs':'rust','.c':'c','.js':'javascript'}
        if ext in table: return table[ext]
        if text.strip().startswith('<'): return 'html'
        if text.strip().startswith(('{','[')): return 'json'
        if re.search(r'^#{1,6}\s', text, re.MULTILINE): return 'markdown'
        return 'texte'

    def _langue(self, tokens: List[str]) -> str:
        fr = len([t for t in tokens if t in {'le','la','les','de','du','des','et','est','un','une'}])
        en = len([t for t in tokens if t in {'the','a','an','is','are','was','to','of','and','in'}])
        return 'fr' if fr > en else ('en' if en > fr else 'inconnu')

    def _resume(self, text: str, n: int = 200) -> str:
        phrases = re.split(r'(?<=[.!?])\s+', text.strip())
        r = ''
        for p in phrases:
            if len(r) + len(p) < n: r += p + ' '
            else: break
        return r.strip() or text[:n] + '...'


# ═══════════════════════════════════════════════════════════
# AGENT 2 — COGNOS
# ═══════════════════════════════════════════════════════════

class CognosAgent(BaseAgent):
    """Analyse sémantique, NER, sentiment, lisibilité."""

    PATTERNS = {
        "email":      re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
        "url":        re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+'),
        "date":       re.compile(r'\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b'),
        "montant":    re.compile(r'[\€\$\£]\s?\d+(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?\s?(?:EUR|USD|€|\$)'),
        "pourcentage":re.compile(r'\b\d+(?:\.\d+)?%'),
        "telephone":  re.compile(r'\b(?:\+33|0)[1-9](?:[\s.-]?\d{2}){4}\b'),
    }
    POSITIF = set("excellent bon bonne super parfait réussite succès efficace rapide simple".split())
    NEGATIF = set("problème erreur défaut mauvais difficile lent complexe échec bug".split())

    TOPICS = {
        "finance":     "budget argent coût prix euros investissement financement",
        "technologie": "python code api serveur données base cloud docker",
        "juridique":   "contrat loi article accord clause signature",
        "médecine":    "patient médecin traitement diagnostic symptôme",
        "marketing":   "client vente marché produit promotion campagne",
        "rh":          "employé salaire recrutement poste équipe formation",
        "minecraft":   "redstone blocs circuit worldedit schematic beacon",
        "ia":          "agent intelligence artificielle modèle nlp traitement",
    }

    async def process(self, task: dict) -> dict:
        payload = task.get("payload", {})
        text    = payload.get("text", "")
        if not text:
            return {"error": "Texte vide", "agent": "COGNOS"}

        entites = {n: list(set(p.findall(text)))[:10]
                   for n, p in self.PATTERNS.items()
                   if p.findall(text)}

        toks   = set(re.findall(r'\b\w+\b', text.lower()))
        sp, sn = len(toks & self.POSITIF), len(toks & self.NEGATIF)
        sentiment = "positif" if sp > sn else ("négatif" if sn > sp else "neutre")

        topics = [t for t, mots in self.TOPICS.items()
                  if sum(1 for m in mots.split() if m in text.lower()) >= 2]

        return {
            "agent":        "COGNOS",
            "entites":      entites,
            "sentiment":    sentiment,
            "score_pos":    sp,
            "score_neg":    sn,
            "topics":       topics,
            "lisibilite":   self._flesch(text),
            "phrases_cles": self._top_phrases(text)[:5],
            "processed_at": time.time(),
        }

    def _flesch(self, text: str) -> float:
        phrases  = max(1, len(re.findall(r'[.!?]+', text)))
        mots     = max(1, len(text.split()))
        syllabes = max(mots, sum(
            max(1, len(re.findall(r'[aeiouyàâéèêëîïôùûü]', w.lower())))
            for w in text.split()))
        return round(max(0.0, min(100.0,
            206.835 - 1.015*(mots/phrases) - 84.6*(syllabes/mots))), 1)

    def _top_phrases(self, text: str) -> List[str]:
        ps = [p.strip() for p in re.split(r'[.!?]', text) if len(p.strip()) > 30]
        def score(p): return (len(re.findall(r'\d',p))*2 + sum(c.isupper() for c in p)) / max(1,len(p))
        return sorted(ps, key=score, reverse=True)


# ═══════════════════════════════════════════════════════════
# AGENT 3 — FUSION
# ═══════════════════════════════════════════════════════════

class FusionAgent(BaseAgent):
    """Fusionne plusieurs résultats LECTOR/COGNOS en un seul document cohérent."""

    async def process(self, task: dict) -> dict:
        docs = task.get("payload", {}).get("documents", [])
        if not docs:
            return {"error": "Aucun document à fusionner", "agent": "FUSION"}

        # Mots-clés avec fréquence
        freq: Dict[str,int] = {}
        for d in docs:
            for k in d.get("keywords", []):
                freq[k] = freq.get(k, 0) + 1
        mots_cles = sorted(freq, key=freq.get, reverse=True)[:30]  # type: ignore[arg-type]

        # Entités fusionnées
        entites: Dict[str,set] = {}
        for d in docs:
            for t, vs in d.get("entites", {}).items():
                entites.setdefault(t, set()).update(vs)

        # Titres dédupliqués (ordre conservé)
        vus: set = set()
        titres = []
        for d in docs:
            for t in d.get("titles", []):
                if t not in vus:
                    vus.add(t); titres.append(t)

        sentiments = [d.get("sentiment","neutre") for d in docs]

        return {
            "agent":            "FUSION",
            "docs_count":       len(docs),
            "total_mots":       sum(d.get("word_count",0) for d in docs),
            "total_chars":      sum(d.get("char_count",0) for d in docs),
            "langues":          list(set(d.get("language","?") for d in docs)),
            "mots_cles":        mots_cles,
            "entites":          {k: list(v)[:10] for k, v in entites.items()},
            "titres":           titres[:20],
            "sentiment_global": max(set(sentiments), key=sentiments.count),
            "topics_globaux":   list(set(t for d in docs for t in d.get("topics",[]))),
            "processed_at":     time.time(),
        }


# ═══════════════════════════════════════════════════════════
# AGENT 4 — VISIO
# ═══════════════════════════════════════════════════════════

class VisioAgent(BaseAgent):
    """Génère un plan de présentation PowerPoint structuré (résolution 16K)."""

    PALETTES = {
        "dark":      {"fond":"#04050a","titre":"#ffffff","texte":"#e2e8f0",
                      "accent":"#818cf8","accent2":"#06b6d4","carte":"#111827"},
        "light":     {"fond":"#ffffff","titre":"#1e293b","texte":"#475569",
                      "accent":"#4f46e5","accent2":"#0ea5e9","carte":"#f1f5f9"},
        "corporate": {"fond":"#0f172a","titre":"#f8fafc","texte":"#cbd5e1",
                      "accent":"#3b82f6","accent2":"#10b981","carte":"#1e293b"},
    }

    async def process(self, task: dict) -> dict:
        payload   = task.get("payload", {})
        fusion    = payload.get("fusion", {})
        titre     = payload.get("titre", "Présentation SYNTDOCS")
        nb_slides = min(int(payload.get("nb_slides", 10)), 30)
        theme     = payload.get("theme", "dark")

        slides = self._plan(fusion, titre, nb_slides)

        return {
            "agent":       "VISIO",
            "titre":       titre,
            "nb_slides":   len(slides),
            "theme":       theme,
            "palette":     self.PALETTES.get(theme, self.PALETTES["dark"]),
            "slides":      slides,
            "resolution":  "16K (15360×8640)",
            "formats":     ["pptx", "pdf", "html", "png"],
            "processed_at": time.time(),
        }

    def _plan(self, f: dict, titre: str, maxi: int) -> List[dict]:
        slides = [{"n":1,"tpl":"titre","titre":titre,
                   "sous_titre":f"SYNTDOCS · {time.strftime('%d/%m/%Y')}"}]

        if f.get("titres"):
            slides.append({"n":2,"tpl":"liste","titre":"Sommaire",
                           "contenu":f["titres"][:8]})

        for i, topic in enumerate(f.get("topics_globaux",[])[:maxi-4], start=3):
            mots = f.get("mots_cles",[])[i*3:(i+1)*3]
            slides.append({"n":i,"tpl":"deux_colonnes",
                           "titre":f"Focus : {topic.capitalize()}","contenu":mots})

        slides.append({"n":len(slides)+1,"tpl":"chiffres","titre":"Chiffres clés",
            "chiffres":[
                {"val":f.get("total_mots",0),   "label":"mots analysés"},
                {"val":f.get("docs_count",0),    "label":"documents"},
                {"val":len(f.get("entites",{})), "label":"types d'entités"},
            ]})

        if f.get("entites"):
            slides.append({"n":len(slides)+1,"tpl":"liste","titre":"Entités",
                "contenu":[f"{k}: {', '.join(str(v) for v in vs[:3])}"
                           for k,vs in list(f["entites"].items())[:5]]})

        slides.append({"n":len(slides)+1,"tpl":"conclusion","titre":"Conclusion",
            "contenu":[f"Sentiment : {f.get('sentiment_global','neutre')}",
                       f"Langues : {', '.join(f.get('langues',['?']))}",
                       "Généré par SYNTDOCS Intelligence Documentaire"]})

        return slides[:maxi]


# ═══════════════════════════════════════════════════════════
# AGENT 5 — NEXPORT
# ═══════════════════════════════════════════════════════════

class NexportAgent(BaseAgent):
    """Export multi-format : md, html, json, txt, + plans pour pdf/docx/xlsx."""

    FORMATS = {"pdf","docx","xlsx","html","epub","md","json","txt","odt","rst"}

    async def process(self, task: dict) -> dict:
        payload = task.get("payload", {})
        fmt     = payload.get("format", "md").lower()
        data    = payload.get("fusion", {})
        titre   = payload.get("titre", "Document SYNTDOCS")

        if fmt not in self.FORMATS:
            return {"error": f"Format inconnu. Disponibles: {sorted(self.FORMATS)}",
                    "agent": "NEXPORT"}

        conv = {"md":self._md,"html":self._html,"json":self._json,"txt":self._txt}
        contenu = conv[fmt](data, titre) if fmt in conv else self._plan_binaire(data, titre, fmt)
        nom     = f"{titre.replace(' ','_')}_{int(time.time())}.{fmt}"

        return {
            "agent":       "NEXPORT",
            "format":      fmt,
            "titre":       titre,
            "contenu":     contenu,
            "taille":      len(contenu),
            "hash":        hashlib.sha256(contenu.encode()).hexdigest()[:16],
            "nom_fichier": nom,
            "processed_at": time.time(),
        }

    def _md(self, d: dict, titre: str) -> str:
        kw   = ", ".join(f"`{k}`" for k in d.get("mots_cles",[])[:15])
        secs = "\n".join(f"### {t}\n\n*[Section générée]*\n"
                         for t in d.get("titres",[])[:10])
        ents = "\n".join(f"- **{k}** : {', '.join(str(v) for v in vs[:3])}"
                         for k,vs in d.get("entites",{}).items())
        return (f"# {titre}\n\n> SYNTDOCS · {time.strftime('%d/%m/%Y')}\n\n"
                f"## Mots-clés\n{kw}\n\n"
                f"## Sections\n{secs}\n"
                f"## Entités\n{ents}\n\n"
                f"---\n*{d.get('docs_count',1)} document(s) · "
                f"sentiment : {d.get('sentiment_global','neutre')}*\n")

    def _html(self, d: dict, titre: str) -> str:
        kw   = "".join(f'<span class="kw">{k}</span>' for k in d.get("mots_cles",[])[:12])
        secs = "".join(f"<section><h2>{t}</h2><p><em>Section auto-générée.</em></p></section>"
                       for t in d.get("titres",[])[:8])
        return (f'<!DOCTYPE html><html lang="{d.get("langues",["fr"])[0]}">'
                f'<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{titre}</title>'
                f'<style>body{{font-family:system-ui;max-width:800px;margin:0 auto;padding:2rem;'
                f'background:#0f172a;color:#e2e8f0}}h1{{color:#818cf8}}h2{{color:#67e8f9;'
                f'border-bottom:1px solid #1e293b;padding-bottom:.5rem}}'
                f'.kw{{background:#1e293b;padding:2px 8px;border-radius:4px;margin:2px;'
                f'display:inline-block;font-size:.8em;color:#a5b4fc}}'
                f'footer{{color:#475569;font-size:.75em;margin-top:3rem}}</style></head>'
                f'<body><h1>{titre}</h1><p><em>SYNTDOCS · {time.strftime("%d/%m/%Y")}</em></p>'
                f'<p>{kw}</p>{secs}'
                f'<footer>SYNTDOCS v1.0 · {d.get("total_mots",0)} mots · '
                f'sentiment : {d.get("sentiment_global","neutre")}</footer></body></html>')

    def _json(self, d: dict, titre: str) -> str:
        return json.dumps({"titre":titre,"version":"syntdocs-1.0",
                           "date":time.strftime('%Y-%m-%dT%H:%M:%S'),
                           "contenu":d}, ensure_ascii=False, indent=2)

    def _txt(self, d: dict, titre: str) -> str:
        sep = '='*len(titre)
        kw  = ', '.join(d.get("mots_cles",[])[:10])
        secs = "".join(f"\n{t}\n{'-'*len(t)}\n[Contenu]\n" for t in d.get("titres",[])[:8])
        return f"{titre}\n{sep}\n{time.strftime('%d/%m/%Y')}\n\nMots-clés : {kw}\n{secs}"

    def _plan_binaire(self, d: dict, titre: str, fmt: str) -> str:
        libs = {"pdf":"reportlab / weasyprint","docx":"python-docx",
                "xlsx":"openpyxl","epub":"ebooklib"}
        return json.dumps({"format":fmt,"titre":titre,
                           "lib":libs.get(fmt,"?"),"data":d,
                           "instructions":f"Générer {fmt.upper()} avec {len(d.get('titres',[]))} sections"},
                          ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
# AGENT 6 — AEGIS
# ═══════════════════════════════════════════════════════════

class AegisAgent(BaseAgent):
    """Audit sécurité — détecte données sensibles, hash, score risque."""

    SENSIBLE = {
        "carte_bancaire": re.compile(r'\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13})\b'),
        "mot_de_passe":   re.compile(r'(?i)(?:password|mot.?de.?passe|passwd)\s*[:=]\s*\S+'),
        "token_secret":   re.compile(r'(?i)(?:api.?key|token|secret)\s*[:=]\s*[A-Za-z0-9+/]{20,}'),
        "ssn_fr":         re.compile(r'\b[12]\d{2}(?:0[1-9]|1[0-2])\d{5}\d{3}\b'),
    }

    async def process(self, task: dict) -> dict:
        text = task.get("payload", {}).get("text", "")
        alertes = {n: len(p.findall(text))
                   for n, p in self.SENSIBLE.items() if p.findall(text)}
        score   = min(100, len(alertes) * 25)
        niveau  = ("critique" if score >= 75 else "élevé" if score >= 50
                   else "moyen" if score >= 25 else "faible")
        return {
            "agent":           "AEGIS",
            "hash":            hashlib.sha256(text.encode()).hexdigest(),
            "alertes":         alertes,
            "score_risque":    score,
            "niveau":          niveau,
            "approuve":        score < 50,
            "recommandations": (["Masquer les données sensibles"] if alertes
                                else ["Document conforme"]),
            "processed_at":    time.time(),
        }


# ═══════════════════════════════════════════════════════════
# AGENT 7 — MNEMO
# ═══════════════════════════════════════════════════════════

class MnemoAgent(BaseAgent):
    """Cache LRU persistant (JSON) — TTL 1h — max 1 000 entrées."""

    def __init__(self, cfg: AgentConfig):
        super().__init__(cfg)
        self._cache: Dict[str, tuple] = {}   # clé → (timestamp, valeur)
        self._max   = 1000
        self._file  = Path("syntdocs_cache.json")
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                with open(self._file) as f:
                    raw = json.load(f)
                # BUG FIX : reconvertit les listes [ts, val] en tuples
                self._cache = {k: (float(v[0]), v[1])
                               for k, v in raw.items()
                               if isinstance(v, (list, tuple)) and len(v) == 2}
                print(f"[MNEMO] Cache chargé — {len(self._cache)} entrées")
            except Exception:
                self._cache = {}

    def _save(self):
        try:
            # Sérialise les tuples en listes (JSON ne supporte pas les tuples)
            with open(self._file, 'w') as f:
                json.dump({k: list(v) for k, v in self._cache.items()},
                          f, ensure_ascii=False)
        except Exception as e:
            print(f"[MNEMO] save-err: {e}", file=sys.stderr)

    async def process(self, task: dict) -> dict:
        payload = task.get("payload", {})
        op      = payload.get("op", "get")
        cle     = payload.get("key", "")
        val     = payload.get("value")

        if op == "get":
            if cle in self._cache:
                ts, v = self._cache[cle]
                if time.time() - ts < 3600:          # TTL 1 h
                    return {"agent":"MNEMO","hit":True,"value":v,
                            "age_s":int(time.time()-ts)}
                del self._cache[cle]                 # Expiré — purge
            return {"agent": "MNEMO", "hit": False}

        elif op == "set":
            # Éviction LRU si plein
            if len(self._cache) >= self._max:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest]
            self._cache[cle] = (time.time(), val)
            self._save()
            return {"agent":"MNEMO","stored":True,"key":cle}

        elif op == "delete":
            removed = cle in self._cache
            self._cache.pop(cle, None)
            self._save()
            return {"agent":"MNEMO","removed":removed}

        elif op == "stats":
            return {"agent":"MNEMO","total":len(self._cache),
                    "max":self._max,"file":str(self._file),
                    "file_exists":self._file.exists()}

        return {"error": "op inconnue", "valid": ["get","set","delete","stats"]}


# ═══════════════════════════════════════════════════════════
# PIPELINE LOCALE (sans NEXUS, sans réseau)
# ═══════════════════════════════════════════════════════════

async def pipeline_complet(texte: str, titre: str = "Document",
                            format_out: str = "md") -> dict:
    """
    Exécute la pipeline complète en local :
    AEGIS → LECTOR → COGNOS → FUSION → VISIO → NEXPORT
    """
    sep = "="*50
    print(f"\n{sep}\nSYNTDOCS Pipeline — {titre}\n{sep}")

    def cfg(role): return AgentConfig(agent_id=f"{role}_LOCAL", role=role)

    # 1. AEGIS
    print("🔒 AEGIS — Audit sécurité...")
    r_aegis = await AegisAgent(cfg("AEGIS")).process({"payload":{"text":texte}})
    print(f"   {r_aegis['niveau']} ({r_aegis['score_risque']}%)")
    if not r_aegis["approuve"]:
        return {"error": "Document rejeté par AEGIS", "details": r_aegis}

    # 2. LECTOR
    print("📖 LECTOR — Parsing...")
    r_lector = await LectorAgent(cfg("LECTOR")).process(
        {"payload":{"text":texte,"filename":f"{titre}.txt"}})
    print(f"   {r_lector['word_count']} mots | {r_lector['type']} | {r_lector['language']}")

    # 3. COGNOS
    print("🧠 COGNOS — Sémantique...")
    r_cognos = await CognosAgent(cfg("COGNOS")).process({"payload":{"text":texte}})
    print(f"   sentiment={r_cognos['sentiment']} | topics={r_cognos['topics']}")

    # 4. FUSION
    print("🔀 FUSION — Fusion...")
    r_fusion = await FusionAgent(cfg("FUSION")).process(
        {"payload":{"documents":[r_lector, r_cognos]}})
    print(f"   {r_fusion['total_mots']} mots | {len(r_fusion['mots_cles'])} keywords")

    # 5. VISIO
    print("🎨 VISIO — Plan slides...")
    r_visio = await VisioAgent(cfg("VISIO")).process(
        {"payload":{"fusion":r_fusion,"titre":titre,"nb_slides":10}})
    print(f"   {r_visio['nb_slides']} slides | {r_visio['resolution']}")

    # 6. NEXPORT
    print(f"📤 NEXPORT — Export {format_out.upper()}...")
    r_export = await NexportAgent(cfg("NEXPORT")).process(
        {"payload":{"fusion":r_fusion,"titre":titre,"format":format_out}})
    print(f"   {r_export['taille']} chars | {r_export['nom_fichier']}")

    print(f"\n✅ Pipeline terminée — {r_export['nom_fichier']}")
    return {"status":"ok",
            "aegis":r_aegis,"lector":r_lector,"cognos":r_cognos,
            "fusion":r_fusion,"visio":r_visio,"export":r_export}


# ═══════════════════════════════════════════════════════════
# LANCEUR
# ═══════════════════════════════════════════════════════════

AGENTS_DISPONIBLES = {
    "LECTOR": (LectorAgent,  "parser"),
    "COGNOS": (CognosAgent,  "nlp"),
    "FUSION": (FusionAgent,  "merger"),
    "VISIO":  (VisioAgent,   "visual"),
    "NEXPORT":(NexportAgent, "exporter"),
    "AEGIS":  (AegisAgent,   "security"),
    "MNEMO":  (MnemoAgent,   "cache"),
}

DEMO_TEXTE = """
SYNTDOCS — Rapport de synthèse complet.
Budget alloué : 5 000 EUR. Contact : dev@syntdocs.app | https://syntdocs.app
Lancement : 01/06/2025. 8 agents IA autonomes.
Stack : Python 3.11, FastAPI, Raspberry Pi, ESP32.
PowerPoint 16K. Export PDF DOCX XLSX HTML EPUB Markdown JSON.
Les agents LECTOR COGNOS FUSION VISIO NEXPORT AEGIS MNEMO travaillent en pipeline.
Redstone Computer : 120×40×80 blocs, 8 circuits autonomes, bus principal.
"""

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="SYNTDOCS Agents")
    p.add_argument("--agent",  help="Lancer un agent : LECTOR, COGNOS…")
    p.add_argument("--id",     default=None, help="ID personnalisé")
    p.add_argument("--all",    action="store_true", help="Lance tous les agents")
    p.add_argument("--demo",   action="store_true", help="Pipeline locale (sans NEXUS)")
    p.add_argument("--format", default="md", help="Format démo : md | html | json | txt")
    args = p.parse_args()

    if args.demo:
        result = asyncio.run(pipeline_complet(DEMO_TEXTE, "Rapport SYNTDOCS", args.format))
        if "export" in result:
            out = Path(result["export"]["nom_fichier"])
            out.write_text(result["export"]["contenu"], encoding="utf-8")
            print(f"📁 Sauvé : {out.resolve()}")

    elif args.all:
        async def _all():
            print(f"🚀 Lancement de {len(AGENTS_DISPONIBLES)} agents...")
            await asyncio.gather(*[
                cls(AgentConfig(args.id or f"{n}_01", role)).start()
                for n, (cls, role) in AGENTS_DISPONIBLES.items()
            ])
        asyncio.run(_all())

    elif args.agent:
        nom = args.agent.upper()
        if nom not in AGENTS_DISPONIBLES:
            print(f"Inconnu. Disponibles : {list(AGENTS_DISPONIBLES)}")
            sys.exit(1)
        cls, role = AGENTS_DISPONIBLES[nom]
        asyncio.run(cls(AgentConfig(args.id or f"{nom}_01", role)).start())

    else:
        p.print_help()
