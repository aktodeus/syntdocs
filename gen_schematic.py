#!/usr/bin/env python3
"""
SYNTDOCS — Générateur de Schematic Redstone WorldEdit
======================================================
Génère un fichier .schem importable dans Minecraft Java 1.20+
via WorldEdit ou Litematica.

Les 8 agents SYNTDOCS sont représentés comme circuits Redstone autonomes
interconnectés par un bus Redstone principal (message queue physique).

Prérequis :
    pip install nbtlib numpy

Usage :
    python3 gen_schematic.py
    → Output : syntdocs_redstone.schem

Import dans Minecraft :
    1. Copier syntdocs_redstone.schem dans /plugins/WorldEdit/schematics/
    2. Dans le jeu : //schem load syntdocs_redstone
    3. //paste -n (sans air pour ne pas effacer le terrain)
"""

import sys
import time
from pathlib import Path

# ── Imports avec fallback gracieux ──
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[WARN] numpy absent — pip install numpy")

try:
    import nbtlib
    from nbtlib.tag import (
        Compound, Int, Short, Long, String, IntArray, List as NbtList
    )
    HAS_NBTLIB = True
except ImportError:
    HAS_NBTLIB = False
    print("[WARN] nbtlib absent — pip install nbtlib")


# ══════════════════════════════════════════════════════════
# PALETTE DE BLOCS MINECRAFT
# Chaque bloc représente un rôle dans l'architecture SYNTDOCS
# ══════════════════════════════════════════════════════════

PALETTE = {
    # Blocs de fondation et structure
    "minecraft:air":              0,
    "minecraft:stone":            1,   # Fondation neutre
    "minecraft:smooth_stone":     2,   # Planchers agents

    # Blocs signifiants — Agents
    "minecraft:gold_block":       3,   # NEXUS — Orchestrateur (Or = maître)
    "minecraft:lapis_block":      4,   # MNEMO — Mémoire (Lapis = bleu RAM)
    "minecraft:emerald_block":    5,   # NEXPORT — Output (Émeraude = export)
    "minecraft:diamond_block":    6,   # AEGIS — Sécurité (Diamant = dur)
    "minecraft:enchanting_table": 7,   # COGNOS — NLP (Table d'enchantement = magie)
    "minecraft:crafting_table":   8,   # FUSION — Assemblage (Table de craft)
    "minecraft:bookshelf":        9,   # LECTOR — Lecture (Bibliothèque)
    "minecraft:white_concrete":   10,  # VISIO — Visuel (Blanc = canvas)

    # Redstone — Signaux et circuits
    "minecraft:redstone_wire":    11,  # Bus de communication
    "minecraft:redstone_torch":   12,  # Horloge / Power source
    "minecraft:redstone_lamp":    13,  # Status LED agents
    "minecraft:comparator":       14,  # Logique de comparaison
    "minecraft:repeater":         15,  # Amplificateur de signal (tous les 15 blocs)
    "minecraft:observer":         16,  # Détecteur d'événements (MNEMO trigger)
    "minecraft:command_block":    17,  # Processeur agent (bloc de commande)

    # Stockage — File de messages
    "minecraft:hopper":           18,  # Queue de messages (items = tâches)
    "minecraft:chest":            19,  # Stockage de résultats
    "minecraft:barrel":           20,  # Formats d'export NEXPORT
    "minecraft:dropper":          21,  # Émission de résultats
    "minecraft:dispenser":        22,  # Filtre de formats

    # Structure spéciale
    "minecraft:obsidian":         23,  # Mur AEGIS (périmètre sécurité)
    "minecraft:iron_door":        24,  # Portes d'accès authentifiées
    "minecraft:glowstone":        25,  # LED de statut (brille = actif)
    "minecraft:quartz_block":     26,  # Tour NIMBUS (cloud = blanc/lumineux)
    "minecraft:beacon":           27,  # Signal NIMBUS uptime (beacon = disponibilité)
    "minecraft:blue_stained_glass": 28, # Rangées RAM MNEMO
    "minecraft:note_block":       29,  # Alarme AEGIS (son = alerte)
}

# Dimensions du monde Redstone
W, H, L = 120, 40, 80   # Width (X) × Height (Y) × Length (Z)

# Positions des agents (x, z) — Y=0 = fondation
POSITIONS_AGENTS = {
    "NEXUS":   (55, 35),   # Centre — Orchestrateur
    "LECTOR":  (55,  5),   # Nord — Lecture
    "COGNOS":  ( 5, 35),   # Ouest — NLP
    "FUSION":  (105, 35),  # Est — Fusion
    "VISIO":   (95,  5),   # Nord-Est — Visuel
    "NEXPORT": (55, 65),   # Sud — Export
    "AEGIS":   ( 0,  0),   # Périmètre entier
    "MNEMO":   (30, 35),   # Centre-Ouest — Mémoire
}

# Tailles des circuits (w, h, d)
TAILLES_AGENTS = {
    "NEXUS":   (10, 8, 10),
    "LECTOR":  ( 8, 6,  8),
    "COGNOS":  ( 8, 6,  8),
    "FUSION":  ( 8, 6,  8),
    "VISIO":   ( 8, 6,  8),
    "NEXPORT": ( 8, 6,  8),
    "MNEMO":   (12, 6, 12),
}


# ══════════════════════════════════════════════════════════
# GÉNÉRATEUR PRINCIPAL
# ══════════════════════════════════════════════════════════

def gen_schematic():
    """
    Génère la structure 3D complète du SYNTDOCS Redstone Computer.
    Retourne un tableau numpy 3D (H, L, W) d'IDs de blocs.
    """
    if not HAS_NUMPY:
        print("❌ numpy requis — pip install numpy")
        return None

    # Tableau 3D initialisé à air
    blocks = np.zeros((H, L, W), dtype=np.int32)

    # ── FONDATION (Y=0 — toute la surface) ──
    blocks[0, :, :] = PALETTE["minecraft:stone"]

    # ── PLANCHERS AGENTS (Y=1) ──
    blocks[1, :, :] = PALETTE["minecraft:smooth_stone"]

    # ── CIRCUIT NEXUS (centre) ──
    _placer_nexus(blocks)

    # ── CIRCUITS AGENTS SECONDAIRES ──
    _placer_lector(blocks)
    _placer_cognos(blocks)
    _placer_fusion(blocks)
    _placer_visio(blocks)
    _placer_nexport(blocks)
    _placer_mnemo(blocks)

    # ── MUR OBSIDIAN AEGIS (périmètre) ──
    _placer_aegis(blocks)

    # ── BUS REDSTONE PRINCIPAL (Y=2) ──
    _placer_bus_redstone(blocks)

    # ── TOUR NIMBUS (Y=8-28 au centre) ──
    _placer_nimbus(blocks)

    # ── PANNEAU DE CONTRÔLE (Y=2, bord sud) ──
    _placer_panneau_controle(blocks)

    # ── PORTES LOGIQUES DANS LE BUS ──
    _placer_portes_logiques(blocks)

    print(f"✓ Structure générée — {W}×{H}×{L} = {W*H*L:,} blocs")
    print(f"  Blocs non-air : {int(np.sum(blocks != 0)):,}")
    return blocks


def _placer_nexus(blocks):
    """NEXUS — Bloc d'or central, commande + glowstone."""
    nx, nz = POSITIONS_AGENTS["NEXUS"]
    for y in range(1, 9):
        for dz in range(10):
            for dx in range(10):
                blocks[y, nz+dz, nx+dx] = PALETTE["minecraft:gold_block"]

    # Bloc de commande au centre (processeur)
    blocks[5, nz+5, nx+5] = PALETTE["minecraft:command_block"]
    # Glowstone au sommet (LED status)
    for dz in range(1, 9):
        for dx in range(1, 9):
            blocks[8, nz+dz, nx+dx] = PALETTE["minecraft:glowstone"]
    # Redstone Torch horloge
    blocks[1, nz+1, nx+1] = PALETTE["minecraft:redstone_torch"]
    blocks[1, nz+1, nx+8] = PALETTE["minecraft:redstone_torch"]
    # Hoppers — file de tâches
    for i in range(4):
        blocks[2, nz+2, nx+2+i] = PALETTE["minecraft:hopper"]
    # Chest — résultats
    blocks[2, nz+7, nx+5] = PALETTE["minecraft:chest"]
    blocks[2, nz+7, nx+6] = PALETTE["minecraft:chest"]


def _placer_agent_generique(blocks, nom: str, bloc_fond: str):
    """Pose un circuit agent générique à sa position."""
    if nom not in POSITIONS_AGENTS:
        return
    ax, az = POSITIONS_AGENTS[nom]
    aw, ah, ad = TAILLES_AGENTS.get(nom, (8, 6, 8))

    for y in range(1, ah+1):
        for dz in range(ad):
            for dx in range(aw):
                blocks[y, az+dz, ax+dx] = PALETTE[bloc_fond]

    # Bloc de commande au centre
    cx, cz = ax + aw//2, az + ad//2
    blocks[ah//2, cz, cx] = PALETTE["minecraft:command_block"]
    # Glowstone status
    blocks[ah, cz, cx] = PALETTE["minecraft:glowstone"]
    # Redstone torch horloge
    blocks[1, az+1, ax+1] = PALETTE["minecraft:redstone_torch"]
    # Hoppers input/output
    blocks[2, az+1, ax + aw//2] = PALETTE["minecraft:hopper"]
    blocks[2, az + ad-2, ax + aw//2] = PALETTE["minecraft:dropper"]


def _placer_lector(blocks):
    """LECTOR — Bibliothèques et hoppers d'ingestion."""
    _placer_agent_generique(blocks, "LECTOR", "minecraft:bookshelf")
    ax, az = POSITIONS_AGENTS["LECTOR"]
    # Rangées de bibliothèques (symbolisent les documents)
    for i in range(6):
        blocks[3, az+1, ax+1+i] = PALETTE["minecraft:bookshelf"]
    # Dispenseur filtre formats
    blocks[2, az+3, ax+4] = PALETTE["minecraft:dispenser"]


def _placer_cognos(blocks):
    """COGNOS — Table d'enchantement + comparateurs."""
    _placer_agent_generique(blocks, "COGNOS", "minecraft:enchanting_table")
    ax, az = POSITIONS_AGENTS["COGNOS"]
    # Comparateurs (seuils de confiance NLP)
    for i in range(3):
        blocks[2, az+2, ax+2+i] = PALETTE["minecraft:comparator"]
    # Blocs de lapis (mémoire NLP)
    for i in range(4):
        blocks[3, az+4, ax+2+i] = PALETTE["minecraft:lapis_block"]


def _placer_fusion(blocks):
    """FUSION — Tables de craft + brewing stand."""
    _placer_agent_generique(blocks, "FUSION", "minecraft:crafting_table")
    ax, az = POSITIONS_AGENTS["FUSION"]
    # Brewing stand (mélange / fusion)
    blocks[2, az+3, ax+4] = PALETTE["minecraft:chest"]
    # Hoppers convergents (plusieurs entrées)
    for i in range(3):
        blocks[2, az+1+i, ax+2] = PALETTE["minecraft:hopper"]


def _placer_visio(blocks):
    """VISIO — Béton blanc + canvas."""
    _placer_agent_generique(blocks, "VISIO", "minecraft:white_concrete")
    ax, az = POSITIONS_AGENTS["VISIO"]
    # Terraccota de couleurs (palette visuelle)
    couleurs = [
        "minecraft:white_concrete", "minecraft:blue_stained_glass",
        "minecraft:gold_block",     "minecraft:emerald_block",
    ]
    for i, couleur in enumerate(couleurs):
        blocks[2, az+2, ax+1+i*2] = PALETTE[couleur]


def _placer_nexport(blocks):
    """NEXPORT — Barils (8 formats d'export)."""
    _placer_agent_generique(blocks, "NEXPORT", "minecraft:emerald_block")
    ax, az = POSITIONS_AGENTS["NEXPORT"]
    # 8 barils = 8 formats (PDF DOCX XLSX HTML EPUB MD JSON TXT)
    for i in range(8):
        x = ax + i % 4
        z = az + 2 + (i // 4) * 2
        if 0 <= z < L and 0 <= x < W:
            blocks[2, z, x] = PALETTE["minecraft:barrel"]


def _placer_mnemo(blocks):
    """MNEMO — Rangées de lapis (RAM simulée) + observers."""
    ax, az = POSITIONS_AGENTS["MNEMO"]

    # Fondation
    for y in range(1, 7):
        for dz in range(12):
            for dx in range(12):
                blocks[y, az+dz, ax+dx] = PALETTE["minecraft:lapis_block"]

    # 8 rangées × 16 blocs de verre bleu = 128 "bits" de RAM simulée
    for row in range(8):
        for bit in range(16):
            if bit < 12:
                blocks[row % 4 + 2, az + 2 + row, ax + bit] = PALETTE["minecraft:blue_stained_glass"]

    # Observers (triggers de cache)
    for i in range(4):
        blocks[2, az+1, ax+2+i*2] = PALETTE["minecraft:observer"]

    # Bloc de commande
    blocks[4, az+6, ax+6] = PALETTE["minecraft:command_block"]
    blocks[6, az+6, ax+6] = PALETTE["minecraft:glowstone"]
    # Cache chest
    for i in range(6):
        blocks[2, az+10, ax+1+i*2] = PALETTE["minecraft:chest"]


def _placer_aegis(blocks):
    """AEGIS — Mur d'obsidienne sur le périmètre complet + note blocks + portes."""
    # Murs Nord et Sud
    for x in range(W):
        for y in range(6):
            blocks[y, 0,   x] = PALETTE["minecraft:obsidian"]
            blocks[y, L-1, x] = PALETTE["minecraft:obsidian"]

    # Murs Est et Ouest
    for z in range(L):
        for y in range(6):
            blocks[y, z, 0  ] = PALETTE["minecraft:obsidian"]
            blocks[y, z, W-1] = PALETTE["minecraft:obsidian"]

    # Note blocks (alarmes) aux coins
    for (cx, cz) in [(1, 1), (1, L-2), (W-2, 1), (W-2, L-2)]:
        blocks[6, cz, cx] = PALETTE["minecraft:note_block"]

    # Portes d'accès (tripwires simulés par iron doors)
    # Porte Nord
    blocks[1, 0, W//2]   = PALETTE["minecraft:iron_door"]
    blocks[2, 0, W//2]   = PALETTE["minecraft:iron_door"]
    # Porte Sud
    blocks[1, L-1, W//2] = PALETTE["minecraft:iron_door"]
    blocks[2, L-1, W//2] = PALETTE["minecraft:iron_door"]

    # Redstone wire tripwire
    for x in range(1, W-1):
        blocks[1, 1, x] = PALETTE["minecraft:redstone_wire"]
        blocks[1, L-2, x] = PALETTE["minecraft:redstone_wire"]


def _placer_bus_redstone(blocks):
    """
    Bus Redstone principal — 3 canaux parallèles (Y=2).
    Connecte tous les agents avec des repeaters tous les 15 blocs.
    """
    BUS_Y = 2

    # Bus horizontal principal (Z=35, tout X)
    for x in range(5, W-5):
        blocks[BUS_Y, 35, x] = PALETTE["minecraft:redstone_wire"]

    # Repeaters tous les 15 blocs (amplifient le signal)
    for x in range(15, W-5, 15):
        blocks[BUS_Y, 35, x] = PALETTE["minecraft:repeater"]

    # Bus vertical principal (X=55, tout Z)
    for z in range(5, L-5):
        blocks[BUS_Y, z, 55] = PALETTE["minecraft:redstone_wire"]
        if z % 15 == 0:
            blocks[BUS_Y, z, 55] = PALETTE["minecraft:repeater"]

    # Connexions agents → bus
    connexions = [
        # (agent_x, agent_z, direction)
        (55, 15, 'z'),   # LECTOR → NEXUS
        (13, 35, 'x'),   # COGNOS → NEXUS
        (97, 35, 'x'),   # FUSION → NEXUS
        (55, 57, 'z'),   # NEXPORT → NEXUS
        (42, 35, 'x'),   # MNEMO → NEXUS
        (95, 15, 'x'),   # VISIO → bus
    ]

    for ax, az, direction in connexions:
        if direction == 'z':
            for dz in range(min(abs(35 - az) + 1, 20)):
                z = az + dz if az < 35 else az - dz
                if 0 < z < L:
                    blocks[BUS_Y, z, ax] = PALETTE["minecraft:redstone_wire"]
        else:
            for dx in range(min(abs(55 - ax) + 1, 20)):
                x = ax + dx if ax < 55 else ax - dx
                if 0 < x < W:
                    blocks[BUS_Y, az, x] = PALETTE["minecraft:redstone_wire"]


def _placer_nimbus(blocks):
    """NIMBUS — Tour Quartz centrale symbolisant le cloud (Y=8-28)."""
    cx, cz = 55, 35
    for y in range(8, 28):
        r = max(1, 3 - (y - 8) // 5)  # Rétrécit en hauteur (forme de tour)
        for dz in range(-r, r+1):
            for dx in range(-r, r+1):
                if abs(dx) == r or abs(dz) == r:  # Seulement les bords
                    z, x = cz+dz, cx+dx
                    if 0 < z < L and 0 < x < W:
                        blocks[y, z, x] = PALETTE["minecraft:quartz_block"]

    # Beacon au sommet (uptime indicator)
    blocks[28, cz, cx] = PALETTE["minecraft:beacon"]
    # Glowstone sous le beacon (active le beacon)
    blocks[27, cz, cx] = PALETTE["minecraft:glowstone"]
    # Pyramide de fer pour le beacon (Y=8-11)
    for y in range(8, 12):
        r = 11 - y
        for dz in range(-r, r+1):
            for dx in range(-r, r+1):
                z, x = cz+dz, cx+dx
                if 0 < z < L and 0 < x < W and blocks[y, z, x] == 0:
                    blocks[y, z, x] = PALETTE["minecraft:stone"]


def _placer_panneau_controle(blocks):
    """Panneau de contrôle — levers + redstone lamps pour chaque agent."""
    py = 2   # Hauteur Y du panneau
    pz = 75  # Position Z (bord sud)

    # 8 lampes = 8 agents
    noms_agents = ["NEXUS", "LECTOR", "COGNOS", "FUSION", "VISIO", "NEXPORT", "AEGIS", "MNEMO"]
    for i, nom in enumerate(noms_agents):
        x = 45 + i * 3
        if x < W-2:
            # Lampe Redstone (état agent)
            blocks[py,   pz, x] = PALETTE["minecraft:redstone_lamp"]
            # Wire en dessous
            blocks[py-1, pz, x] = PALETTE["minecraft:redstone_wire"]
            # Comparateur (mesure la charge)
            blocks[py, pz+1, x] = PALETTE["minecraft:comparator"]


def _placer_portes_logiques(blocks):
    """
    Porte logiques AND, OR, NOT dans le bus — à Y=3.
    Représentent la logique de routage des tâches.
    """
    gates_y = 3

    # Porte AND (intersection COGNOS → FUSION)
    bx, bz = 40, 35
    blocks[gates_y, bz,   bx]   = PALETTE["minecraft:redstone_torch"]
    blocks[gates_y, bz,   bx+1] = PALETTE["minecraft:redstone_torch"]
    blocks[gates_y, bz+1, bx]   = PALETTE["minecraft:redstone_wire"]
    blocks[gates_y, bz+1, bx+1] = PALETTE["minecraft:redstone_wire"]

    # Porte NOT (inverseur AEGIS)
    bx, bz = 10, 35
    blocks[gates_y, bz, bx]   = PALETTE["minecraft:redstone_torch"]
    blocks[gates_y, bz, bx+1] = PALETTE["minecraft:redstone_wire"]

    # RS-Latch (mémoire d'état agent — 1 bit par agent)
    for i in range(8):
        bx = 45 + i * 3
        bz = 70
        if bx < W - 2:
            blocks[gates_y, bz,   bx] = PALETTE["minecraft:redstone_torch"]
            blocks[gates_y, bz+1, bx] = PALETTE["minecraft:redstone_torch"]
            blocks[gates_y, bz,   bx+1] = PALETTE["minecraft:redstone_wire"]


# ══════════════════════════════════════════════════════════
# SÉRIALISATION NBT → .schem WorldEdit
# ══════════════════════════════════════════════════════════

def sauver_schematic(blocks, nom_fichier: str = "syntdocs_redstone.schem"):
    """
    Sérialise la structure 3D en fichier .schem WorldEdit.
    Format : WorldEdit Schematic v2 (NBT)
    """
    if not HAS_NBTLIB:
        print("❌ nbtlib requis — pip install nbtlib")
        return False

    print(f"📦 Sérialisation NBT ({W}×{H}×{L} blocs)...")

    # Palette inversée : ID → nom
    palette_inverse = {v: k for k, v in PALETTE.items()}
    # Seulement les blocs utilisés
    ids_utilises = set(int(blocks[y, z, x])
                       for y in range(H)
                       for z in range(L)
                       for x in range(W))

    # Palette NBT (seulement les blocs présents)
    palette_nbt = Compound({
        palette_inverse[bid]: Int(i)
        for i, bid in enumerate(sorted(ids_utilises))
        if bid in palette_inverse
    })

    # Remapping des IDs
    remap = {bid: i for i, bid in enumerate(sorted(ids_utilises))}
    flat = [remap.get(int(blocks[y, z, x]), 0)
            for y in range(H)
            for z in range(L)
            for x in range(W)]

    # Structure NBT WorldEdit Schematic v2
    schematic = Compound({
        "Version":     Int(2),
        "DataVersion": Int(3120),   # Minecraft Java 1.20
        "Width":       Short(W),
        "Height":      Short(H),
        "Length":      Short(L),
        "PaletteMax":  Int(len(ids_utilises)),
        "Palette":     palette_nbt,
        "BlockData":   IntArray(flat),
        "BlockEntities": NbtList([]),
        "Metadata":    Compound({
            "Name":        String("SYNTDOCS Redstone Computer"),
            "Author":      String("SYNTDOCS"),
            "Description": String("8 agents IA représentés comme circuits Redstone"),
            "Date":        Long(int(time.time() * 1000)),
            "WEOffsetX":   Int(-W // 2),
            "WEOffsetY":   Int(0),
            "WEOffsetZ":   Int(-L // 2),
        }),
    })

    nbt_file = nbtlib.File({"Schematic": schematic})
    nbt_file.save(nom_fichier)

    taille = Path(nom_fichier).stat().st_size
    print(f"✅ {nom_fichier} généré — {taille / 1024:.1f} KB")
    print(f"   Blocs uniques : {len(ids_utilises)}")
    print(f"   Blocs non-air : {int(sum(1 for v in flat if v != 0)):,}")
    return True


def generer_resume_ascii(blocks):
    """
    Génère une carte ASCII du plan Y=2 pour vérification visuelle.
    Affiché dans le terminal.
    """
    print("\n═══ Carte ASCII Y=2 (bus Redstone) ═══")
    symboles = {
        PALETTE["minecraft:air"]:            '·',
        PALETTE["minecraft:redstone_wire"]:  '─',
        PALETTE["minecraft:repeater"]:       '►',
        PALETTE["minecraft:gold_block"]:     'N',  # NEXUS
        PALETTE["minecraft:bookshelf"]:      'L',  # LECTOR
        PALETTE["minecraft:enchanting_table"]:'C', # COGNOS
        PALETTE["minecraft:crafting_table"]: 'F',  # FUSION
        PALETTE["minecraft:white_concrete"]: 'V',  # VISIO
        PALETTE["minecraft:emerald_block"]:  'X',  # NEXPORT
        PALETTE["minecraft:obsidian"]:       '#',  # AEGIS
        PALETTE["minecraft:lapis_block"]:    'M',  # MNEMO
        PALETTE["minecraft:hopper"]:         'h',
        PALETTE["minecraft:command_block"]:  'P',  # Processeur
    }
    # Affiche 1 pixel sur 4 pour tenir dans le terminal
    for z in range(0, L, 4):
        ligne = ""
        for x in range(0, W, 2):
            val = int(blocks[2, z, x])
            ligne += symboles.get(val, '?')
        print(ligne)
    print(f"\nLégende : N=NEXUS L=LECTOR C=COGNOS F=FUSION V=VISIO X=NEXPORT M=MNEMO #=AEGIS")


# ══════════════════════════════════════════════════════════
# ENTRÉE PRINCIPALE
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="SYNTDOCS Redstone Schematic Generator")
    p.add_argument("--output",  default="syntdocs_redstone.schem", help="Fichier de sortie")
    p.add_argument("--preview", action="store_true", help="Affiche la carte ASCII dans le terminal")
    p.add_argument("--dry-run", action="store_true", dest="dry", help="Génère sans sauvegarder")
    args = p.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║  SYNTDOCS Redstone Schematic Generator   ║")
    print(f"║  Monde : {W}×{H}×{L} blocs ({W*H*L//1000}K blocs)   ║")
    print("╚══════════════════════════════════════════╝\n")

    # Génération
    blocks = gen_schematic()
    if blocks is None:
        sys.exit(1)

    # Aperçu ASCII
    if args.preview:
        generer_resume_ascii(blocks)

    # Sauvegarde
    if not args.dry:
        succes = sauver_schematic(blocks, args.output)
        if succes:
            print(f"\n📋 Import dans Minecraft :")
            print(f"   1. Copier {args.output} dans /plugins/WorldEdit/schematics/")
            print(f"   2. Dans le jeu : //schem load syntdocs_redstone")
            print(f"   3. //paste -n (colle sans air)")
    else:
        print("Mode dry-run — fichier non sauvegardé")
