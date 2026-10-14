#!/usr/bin/env python3
"""Génère les schémas d'infrastructure réseau Kubernetes de CinetINT (un SVG par défi).

Le sujet demande, pour chaque défi, un schéma de tous les composants réseau qui participent
au fonctionnement du service. Ce script écrit k8s/defiN/schema.svg pour N = 1 à 16, 18 et 19,
avec la bibliothèque standard seulement.

Usage
  python3 k8s/outils/generer_schemas.py                  # régénère tous les schémas
  python3 k8s/outils/generer_schemas.py --seulement 7    # un seul défi (option répétable)
  python3 k8s/outils/generer_schemas.py --sortie /tmp/x  # écrit dans /tmp/x/defiN/schema.svg
  python3 k8s/outils/generer_schemas.py --debug          # ajoute des attributs de contrôle (data-c, data-box)

Conventions de lecture (identiques d'un défi à l'autre) : or = flux principal, gris = flux interne,
bleu = réseau des Services (ClusterIP), vert = autorisé, rouge = bloqué, bordure or épaisse avec
pastille NOUVEAU = ce que le défi ajoute au précédent. Les IP de pods et de Services sont des exemples.
"""

import argparse
import os
import sys
from xml.sax.saxutils import escape

# ---------------------------------------------------------------- palette
FOND = "#0c0b09"
CARTE = "#16140f"
CARTE2 = "#1d1a13"
BORD = "#3a342a"
OR = "#c0965e"
OR_CLAIR = "#d9b886"
T1 = "#f3ebdd"
T2 = "#d8d0c2"
T3 = "#a39c90"
GRIS = "#8a8377"
VERT = "#6fae78"
ROUGE = "#c4584c"
BLEU = "#6f8fb0"
BLEU_CLAIR = "#9db6cf"
FONT = "Verdana, 'DejaVu Sans', 'Segoe UI', Arial, sans-serif"

COULEURS = {"or": OR, "gris": GRIS, "vert": VERT, "rouge": ROUGE, "bleu": BLEU}

# ---------------------------------------------------------------- mesure de texte (Verdana)
_LARGEURS = {
    "a": .60, "b": .62, "c": .52, "d": .62, "e": .60, "f": .35, "g": .62, "h": .63, "i": .27, "j": .34,
    "k": .59, "l": .27, "m": .97, "n": .63, "o": .61, "p": .62, "q": .62, "r": .43, "s": .52, "t": .39,
    "u": .63, "v": .59, "w": .82, "x": .59, "y": .59, "z": .53,
    " ": .35, ".": .36, ",": .36, ":": .45, ";": .45, "/": .43, "-": .45, "_": .50, "(": .45, ")": .45,
    "'": .28, "|": .53, "=": .84, ">": .84, "<": .84, "+": .84, "*": .50, "#": .84, "%": 1.0, "{": .62,
    "}": .62, "[": .45, "]": .45, "\"": .46, "!": .45, "?": .53, "@": 1.0, "&": .78, "$": .64, "~": .84,
}


def largeur(texte, taille, gras=False):
    """Largeur estimée (px) d'un texte en Verdana ; volontairement un peu large."""
    w = 0.0
    for c in texte:
        if c in _LARGEURS:
            w += _LARGEURS[c]
        elif c.isdigit():
            w += .64
        elif c.isupper():
            w += .74
        else:
            w += .62
    return w * taille * (1.10 if gras else 1.0)


def esc(t):
    return escape(t, {'"': "&quot;"})


# ---------------------------------------------------------------- le schéma
class Schema:
    """Accumule les éléments SVG ; chaque primitive sait mesurer son texte et prévenir d'un débordement."""

    def __init__(self, num, w, h, sous_titre, titre_doc, debug=False):
        self.num, self.w, self.h = num, w, h
        self.sous_titre, self.titre_doc, self.debug = sous_titre, titre_doc, debug
        self.o = []
        self.boites = {}
        self.avert = []
        self.n = 0
        self.marqueurs = set()

    # --- bas niveau
    def brut(self, x):
        self.o.append(x)

    def dc(self):
        return ' data-chip="1"' if self.debug else ""

    def nid(self):
        self.n += 1
        return "b%d" % self.n

    def alerte(self, msg):
        self.avert.append("defi %s : %s" % (self.num, msg))

    def rect(self, x, y, w, h, fill=CARTE, stroke=BORD, sw=1.5, rx=10, dash=None, op=None, bid=None):
        a = ['x="%g" y="%g" width="%g" height="%g" rx="%g"' % (x, y, w, h, rx)]
        a.append('fill="%s"' % fill if fill else 'fill="none"')
        if stroke:
            a.append('stroke="%s" stroke-width="%g"' % (stroke, sw))
        if dash:
            a.append('stroke-dasharray="%s"' % dash)
        if op is not None:
            a.append('opacity="%g"' % op)
        if self.debug and bid:
            a.append('data-box="%s"' % bid)
        self.o.append("<rect %s/>" % " ".join(a))
        if bid:
            self.boites[bid] = (x, y, w, h)

    def ligne(self, x1, y1, x2, y2, stroke=BORD, sw=1, dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        self.o.append('<path d="M%g,%g L%g,%g" fill="none" stroke="%s" stroke-width="%g"%s/>' % (x1, y1, x2, y2, stroke, sw, d))

    def texte(self, x, y, runs, taille=12, fill=T2, gras=False, ancre="start", c=None, chip=False):
        """runs : une chaîne ou une liste de (texte, fill, gras, taille) dans UN SEUL <text> (tspans)."""
        if isinstance(runs, str):
            runs = [(runs, fill, gras, taille)]
        total = 0.0
        parts = []
        for r in runs:
            t = r[0]
            f = r[1] if len(r) > 1 and r[1] else fill
            g = r[2] if len(r) > 2 and r[2] is not None else gras
            sz = r[3] if len(r) > 3 and r[3] else taille
            total += largeur(t, sz, g)
            parts.append('<tspan fill="%s" font-size="%g" font-weight="%s">%s</tspan>' % (f, sz, 700 if g else 400, esc(t)))
        attrs = 'x="%g" y="%g" text-anchor="%s"' % (x, y, ancre)
        if self.debug:
            if c:
                attrs += ' data-c="%s"' % c
            if chip:
                attrs += ' data-chip="1"'
        self.o.append("<text %s>%s</text>" % (attrs, "".join(parts)))
        if c and c in self.boites:
            bx, by, bw, bh = self.boites[c]
            g0, g1 = (x, x + total) if ancre == "start" else ((x - total, x) if ancre == "end" else (x - total / 2, x + total / 2))
            if g0 < bx + 4 or g1 > bx + bw - 4:
                self.alerte("texte hors boîte %s : %s" % (c, "".join(r[0] for r in runs)[:50]))
        return total

    # --- éléments composés
    def boite(self, x, y, w, h, titre=None, lignes=(), stroke=BORD, fill=CARTE, sw=1.5, rx=10, dash=None,
              tfill=T1, tsize=14, droite=None, nouveau=False, ldy=19, lsize=12, op=None, entete=True):
        bid = self.nid()
        if nouveau:
            stroke, sw = OR, 3
        self.rect(x, y, w, h, fill, stroke, sw, rx, dash, op, bid)
        ty = y + 24
        if titre is not None:
            if droite:
                self.texte(x + 14, ty, [(titre, tfill, True, tsize)], c=bid)
                self.texte(x + w - 14, ty, [(droite, T3, False, 12)], ancre="end", c=bid)
            else:
                self.texte(x + 14, ty, [(titre, tfill, True, tsize)], c=bid)
            if lignes and entete:
                self.ligne(x, y + 34, x + w, y + 34, BORD)
            ty = y + 34 + 21
        else:
            ty = y + 22
        for l in lignes:
            if isinstance(l, str) and l == "":
                ty += ldy
                continue
            if isinstance(l, str):
                self.texte(x + 14, ty, [(l, T3, False, lsize)], c=bid)
            elif isinstance(l, tuple):
                self.texte(x + 14, ty, [(l[0], l[1], l[2] if len(l) > 2 else False, lsize)], c=bid)
            else:
                self.texte(x + 14, ty, [(r[0], r[1] if len(r) > 1 else T3, r[2] if len(r) > 2 else False, lsize) for r in l], c=bid)
            ty += ldy
        if nouveau:
            self.pastille(x + w - 84, y - 11)
        return (x, y, w, h)

    def pastille(self, x, y, texte="NOUVEAU"):
        w = largeur(texte, 12, True) + 14
        self.o.append('<rect x="%g" y="%g" width="%g" height="20" rx="10" fill="%s"/>' % (x, y, w, OR))
        self.o.append('<text x="%g" y="%g" text-anchor="middle" fill="%s" font-size="12" font-weight="700"%s>%s</text>' % (x + w / 2, y + 14.5, FOND, self.dc(), texte))

    def cercle(self, cx, cy, lettre, fill=OR, tfill=FOND, stroke=None, r=11):
        s = ' stroke="%s" stroke-width="1.5"' % stroke if stroke else ""
        self.o.append('<circle cx="%g" cy="%g" r="%g" fill="%s"%s/>' % (cx, cy, r, fill, s))
        self.o.append('<text x="%g" y="%g" text-anchor="middle" fill="%s" font-size="12" font-weight="700"%s>%s</text>' % (cx, cy + 4.2, tfill, self.dc(), esc(str(lettre))))

    def etape(self, cx, cy, n):
        self.cercle(cx, cy, n, OR, FOND)

    def appel(self, cx, cy, lettre):
        self.cercle(cx, cy, lettre, FOND, T1, GRIS)

    def chip(self, cx, cy, texte, fill=T2, taille=12, gras=False):
        """Étiquette centrée sur (cx, cy) avec fond opaque (pour poser un libellé sur une ligne)."""
        w = largeur(texte, taille, gras) + 12
        self.o.append('<rect x="%g" y="%g" width="%g" height="20" rx="5" fill="%s" stroke="%s" stroke-width="0.8"/>' % (cx - w / 2, cy - 10, w, FOND, BORD))
        self.texte(cx, cy + 4.2, [(texte, fill, gras, taille)], ancre="middle", chip=True)

    def fleche(self, pts, coul="or", sw=2, dash=None, tete=True, barre=False, ligne_seule=False):
        c = COULEURS.get(coul, coul)
        if tete and not ligne_seule:
            self.marqueurs.add(coul)
        d = "M%g,%g " % pts[0] + " ".join("L%g,%g" % p for p in pts[1:])
        a = 'fill="none" stroke="%s" stroke-width="%g"' % (c, sw)
        if dash:
            a += ' stroke-dasharray="%s"' % dash
        if tete and not ligne_seule:
            a += ' marker-end="url(#m-%s)"' % coul
        if self.debug:
            a += ' data-pts="%s"' % ";".join("%g,%g" % p for p in pts)
        self.o.append('<path d="%s" %s/>' % (d, a))
        if barre:
            (x1, y1), (x2, y2) = pts[-2], pts[-1]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.croix(mx, my)

    def croix(self, cx, cy, coul=ROUGE, r=9):
        self.o.append('<circle cx="%g" cy="%g" r="%g" fill="%s" stroke="%s" stroke-width="2"/>' % (cx, cy, r + 4, FOND, coul))
        self.o.append('<path d="M%g,%g L%g,%g M%g,%g L%g,%g" stroke="%s" stroke-width="3" fill="none"/>' % (cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3, cx - r + 3, cy + r - 3, cx + r - 3, cy - r + 3, coul))

    def coche(self, cx, cy, coul=VERT, r=9):
        self.o.append('<circle cx="%g" cy="%g" r="%g" fill="%s" stroke="%s" stroke-width="2"/>' % (cx, cy, r + 4, FOND, coul))
        self.o.append('<path d="M%g,%g L%g,%g L%g,%g" stroke="%s" stroke-width="3" fill="none"/>' % (cx - 5, cy, cx - 1, cy + 4, cx + 6, cy - 5, coul))

    def cadre(self, x, y, w, h, etiquette=None, stroke=GRIS, dash="6 5", ex=None, ancre="start", ey=None, fill=None, sw=1.2, tfill=GRIS, op=None):
        self.rect(x, y, w, h, fill, stroke, sw, 14, dash, op)
        if etiquette:
            if ex is None:
                ex = x + 16 if ancre == "start" else x + w - 16
            self.texte(ex, ey if ey is not None else y + 21, [(etiquette, tfill, False, 12)], ancre=ancre)

    def pod(self, x, y, w, nom, ip, port=None, extra=None, nouveau=False, fantome=False, h=60, pastille=False, stroke=None, fill=CARTE):
        bid = self.nid()
        dash = "5 4" if fantome else None
        st = stroke or (GRIS if not fantome else GRIS)
        self.rect(x, y, w, h, fill, OR if nouveau else st, 3 if nouveau else 1.2, 8, dash, 0.55 if fantome else None, bid)
        self.texte(x + 10, y + 18, [(nom, T1, True, 12)], c=bid)
        l2 = ip if port is None else "%s  :%s" % (ip, port)
        self.texte(x + 10, y + 35, [(l2, OR_CLAIR, False, 12)], c=bid)
        if extra:
            self.texte(x + 10, y + 52, [(extra, T3, False, 12)], c=bid)
        if nouveau and pastille:
            self.pastille(x + w - 82, y - 15)
        return bid

    def service(self, x, y, w, nom, ip, ports, nouveau=False, h=46, pastille=False, titre="Service ", ligne2=None, fill="#12161a", stroke=None, dash=None):
        bid = self.nid()
        self.rect(x, y, w, h, fill, OR if nouveau else (stroke or BLEU), 3 if nouveau else 1.5, 9, dash, None, bid)
        self.texte(x + 10, y + 19, [(titre, BLEU_CLAIR, False, 12), (nom, T1, True, 13)], c=bid)
        self.texte(x + 10, y + 36, [(ligne2 if ligne2 else "%s  :%s" % (ip, ports), BLEU_CLAIR, False, 12)], c=bid)
        if nouveau and pastille:
            self.pastille(x + w - 82, y + h - 9)
        return bid

    def legende(self, x, y, items, largeur_max=1500, dy=26):
        """items : (genre, couleur, texte). genre = fleche, ligne, boite, nouveau, pod, service."""
        cx, cy = x, y
        for genre, coul, txt in items:
            lw = largeur(txt, 12) + 54
            if cx + lw > x + largeur_max:
                cx, cy = x, cy + dy
            if genre == "fleche":
                self.fleche([(cx, cy), (cx + 34, cy)], coul, 2)
            elif genre == "pointille":
                self.fleche([(cx, cy), (cx + 34, cy)], coul, 2, dash="5 4")
            elif genre == "boite":
                self.rect(cx, cy - 8, 34, 16, CARTE, COULEURS.get(coul, coul), 1.5, 4)
            elif genre == "nouveau":
                self.rect(cx, cy - 8, 34, 16, CARTE, OR, 3, 4)
            elif genre == "service":
                self.rect(cx, cy - 8, 34, 16, "#12161a", BLEU, 1.5, 4)
            elif genre == "fantome":
                self.rect(cx, cy - 8, 34, 16, CARTE, GRIS, 1.2, 4, "4 3", 0.6)
            elif genre == "cercle":
                self.cercle(cx + 17, cy, coul, OR, FOND, r=9)
            self.texte(cx + 44, cy + 4, [(txt, T2, False, 12)])
            cx += lw + 24
        return cy

    def entete(self):
        self.o.insert(0, '<rect width="%d" height="%d" rx="16" fill="%s"/>' % (self.w, self.h, FOND))
        self.o.insert(1, '<text x="50" y="46"><tspan fill="%s" font-size="24" font-weight="600" letter-spacing="3">CINETINT</tspan>'
                      '<tspan dx="16" fill="%s" font-size="15">%s</tspan></text>' % (OR, T3, esc(self.sous_titre)))

    def svg(self):
        defs = []
        for k in sorted(self.marqueurs):
            defs.append('<marker id="m-%s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
                        '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>' % (k, COULEURS.get(k, k)))
        head = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="%s">\n'
                '<title>%s</title>\n<defs>\n%s\n</defs>\n' % (self.w, self.h, self.w, self.h, FONT, esc(self.titre_doc), "\n".join(defs)))
        return head + "\n".join(self.o) + "\n</svg>\n"


# ================================================================ composition commune (défis 3 à 12)
X0, X1 = 60, 1560          # bords des bandes de nœuds
SLOT0 = 282                # début des colonnes de composants
LANE_A, LANE_B = 34, 48    # couloirs des flèches vers l'API server (marge gauche)

DEFIS = {}
APPELS_COURTS = [("A", "front -> back"), ("B", "back -> qr-generator"), ("C", "qr-verifier -> back"),
                 ("D", "qr-verifier -> qr-generator"), ("E", "back -> redis"), ("F", "back -> postgres")]


def defi(num, titre_doc, sous_titre, w=1600, h=1250):
    """Enregistre la fonction qui dessine le schéma du défi num."""
    def deco(fn):
        DEFIS[num] = (w, h, titre_doc, sous_titre, fn)
        return fn
    return deco


def pod_d(n, ip, p=None, x=None, nouveau=False, fantome=False, **kw):
    d = dict(n=n, ip=ip, p=p, x=x, nouveau=nouveau, fantome=fantome)
    d.update(kw)
    return d


def cluster(s, cfg):
    """Dessine le squelette commun : ligne Internet, kube-system, Services, nœuds 2 et 3, nœud 1.

    cfg['slots'] : liste de composants (une colonne chacun) :
      dict(pill=dict(nom, ip, ports, nouveau, titre, ligne2), pods={2: [pod_d...], 3: [pod_d...]},
           routes=[(chemin, dx)])
    Renvoie un dictionnaire de géométrie pour que chaque défi ajoute ses propres éléments.
    """
    N = cfg.get("nouveau", set())
    num = cfg.get("numeros", True)
    slots = cfg["slots"]
    n = len(slots)
    W = (X1 - SLOT0) / n
    ph = cfg.get("pod_h", 60)
    nlev = max([c["lvl"] for c in cfg.get("calls", [])] + [1])
    sm = max([len(sl["pods"].get(k, [])) for sl in slots for k in (2, 3)] + [1])

    rowA_y, rowA_h = 64, 66
    frame_y = 148
    rowB_y, rowB_h = 174, cfg.get("rowB_h", 124)
    rowB_bot = rowB_y + rowB_h
    pill_h = cfg.get("pill_h", 46)
    pill_top = rowB_bot + 30 + 22 + 18 * nlev + 4
    lvl_y = {k: pill_top - 18 * k - 2 for k in range(1, nlev + 1)}
    bus_y = lvl_y[nlev] - 24
    bh = 16 + sm * ph + (sm - 1) * 6 + 22
    band = {2: pill_top + pill_h + 32}
    band[3] = band[2] + bh + 10
    n1_y = band[3] + bh + 10
    n1_h = 100
    frame_h = n1_y + n1_h + 14 - frame_y
    g = dict(W=W, pill_top=pill_top, pill_h=pill_h, lvl_y=lvl_y, bus_y=bus_y, band=band, bh=bh, n1_y=n1_y, n1_h=n1_h,
             frame_bot=frame_y + frame_h, c={}, pill={}, podr={}, ph=ph, slot_x={}, rowB_y=rowB_y, rowB_bot=rowB_bot,
             rowB_h=rowB_h, rowA_y=rowA_y, rowA_h=rowA_h, frame_y=frame_y)

    # --- cadre du cluster
    s.cadre(20, frame_y, 1560, frame_h, cfg.get("etiquette_cluster", "Cluster Kubernetes RKE2 : pods 10.42.0.0/16, Services 10.43.0.0/16"),
            ex=1440, ancre="end", ey=frame_y + 12)

    # --- ligne du haut : poste, navigateur, DNS, chaîne d'entrée
    ing = cfg.get("ingress")
    if cfg.get("poste"):
        s.boite(X0, rowA_y, 290, rowA_h, "Poste du développeur", cfg["poste"]["lignes"], nouveau="poste" in N)
        g["poste"] = (X0, rowA_y, 290, rowA_h)
    if ing == "fantome":
        s.rect(372, rowB_y - 6, 1188, rowB_bot - rowB_y + 6, None, GRIS, 1.5, 12, "6 5")
        s.texte(966, 226, [("Pas encore d'accès depuis Internet", T2, True, 14)], ancre="middle")
        s.texte(966, 250, [("Navigateur, DNS public, MetalLB, Service LoadBalancer et Ingress arrivent au défi 4", T3, False, 12)], ancre="middle")
        g["ingx"] = 1103
    elif ing:
        fant = False
        kw = {}
        s.boite(372, rowA_y, 250, rowA_h, "Navigateur", ["HTTPS vers le nom public"], nouveau="browser" in N, **kw)
        s.boite(660, rowA_y, 520, rowA_h, "DNS public (créé par les enseignants)",
                ["django.<groupe>.csc8567.luxbulb.org -> 157.159.11.201"], nouveau="dns" in N, **kw)
        s.boite(372, rowB_y, 224, rowB_h, "MetalLB (speaker)",
                ["annonce l'IP externe", ("157.159.11.201", OR_CLAIR, True), "attribuée au Service LB", "(adresse du pool du cluster)"],
                nouveau="metallb" in N, **kw)
        s.boite(636, rowB_y, 306, rowB_h, "Service LoadBalancer",
                ["rke2-ingress-nginx-controller", "ClusterIP 10.43.144.159", "80:31324/TCP  443:30747/TCP", "(namespace kube-system)"],
                nouveau="svclb" in N, **kw)
        s.boite(978, rowB_y, 250, rowB_h, "Pod ingress-nginx",
                ["namespace kube-system", "nginx lit les Ingress", "écoute 80 et 443", "choisit selon le chemin"],
                nouveau="ingctrl" in N, **kw)
        s.boite(1256, rowB_y, 304, rowB_h, cfg.get("rules_titre", "Ingress api + site"),
                cfg.get("rules", ["/api -> back:8000", "/qr -> qr-generator:8001", "/verification -> qr-verifier:8002", "/ -> front:8080"]),
                droite="u-XXX", nouveau="rules" in N, **kw)
        if not fant:
            s.fleche([(622, rowA_y + 33), (660, rowA_y + 33)], "gris", dash="5 4")
            if num: s.etape(641, rowA_y + 12, 1)
            s.fleche([(480, rowA_y + rowA_h), (480, rowB_y)], "or")
            if num: s.etape(502, rowA_y + rowA_h + 10, 2)
            s.fleche([(596, rowB_y + 63), (636, rowB_y + 63)], "or")
            s.fleche([(942, rowB_y + 63), (978, rowB_y + 63)], "or")
            if num: s.etape(960, rowB_y + 43, 3)
            s.fleche([(1256, rowB_y + 63), (1228, rowB_y + 63)], "gris", dash="5 4")
        g["ingx"] = 1103
    # --- CoreDNS
    s.boite(X0, rowB_y, 290, rowB_h, "CoreDNS", ["Service kube-dns 10.43.0.10", "résout les noms des Services", "ex. back.u-XXX.svc.cluster.local", "(les pods appellent « back »)"],
            droite="kube-system", nouveau="coredns" in N)

    # --- étiquette de la couche des Services
    s.texte(X0 + 14, pill_top + 36, [("Réseau des Services", BLEU_CLAIR, True, 13)])
    s.texte(X0 + 14, pill_top + 53, [("10.43.0.0/16 (IP virtuelles)", BLEU_CLAIR, False, 12)])
    # --- mini légende des appels entre Services (lettres des cercles gris)
    if cfg.get("calls") and cfg.get("legende_appels", True):
        for k, (lt, t) in enumerate(cfg.get("appels_txt", APPELS_COURTS)):
            yy = rowB_bot + 22 + 17 * k
            s.cercle(X0 + 9, yy - 4, lt, FOND, T1, GRIS, r=9)
            s.texte(X0 + 26, yy, [(t, T2, False, 12)])

    # --- bandes des nœuds
    for k, nom, cidr in ((2, "Node 2 (worker)", "10.42.1.0/24"), (3, "Node 3 (worker)", "10.42.2.0/24")):
        by = band[k]
        s.rect(X0, by, X1 - X0, bh, "#100f0b", GRIS, 1.2, 12)
        s.texte(X0 + 14, by + 25, [(nom, T1, True, 14)])
        nl = cfg.get("node_lines") or ("pods : %s", "kubelet, containerd", "kube-proxy (iptables)", "pont cni0, veth par pod")
        for i, l in enumerate((nl[0] % cidr,) + tuple(nl[1:])):
            s.texte(X0 + 14, by + 46 + 18 * i, [(l, T3, False, 12)])
        s.rect(SLOT0 - 6, by + bh - 16, X1 - SLOT0 + 6 - 12, 8, OR_CLAIR, None, 1, 3, None, 0.45)
    if num:
        s.etape(SLOT0 - 22, band[2] + bh - 12, 7)

    # --- Node 1
    s.rect(X0, n1_y, X1 - X0, n1_h, "#100f0b", GRIS, 1.2, 12)
    s.texte(X0 + 14, n1_y + 22, [("Node 1 (master, control plane)", T1, True, 14), ("   pods 10.42.0.0/24 : aucun pod applicatif ici", T3, False, 12)])
    cards = cfg.get("node1_cards") or [
        ("API server", [":6443, entrée de kubectl", "valide, puis écrit dans etcd"]),
        ("etcd", [":2379, base clé-valeur", "état de tout le cluster"]),
        ("scheduler", ["choisit le nœud", "de chaque nouveau pod"]),
        ("controller-manager", ["Deployment, ReplicaSet,", "boucles de réconciliation"]),
        ("kubelet, kube-proxy", ["sur chaque nœud : lancent", "les pods, règles iptables"]),
    ]
    cx, cw = X0 + 14, 214
    for i, (t, ls) in enumerate(cards):
        nv = t in cfg.get("node1_nouveau", ())
        cid = s.nid()
        s.rect(cx, n1_y + 32, cw, 58, CARTE2, OR if nv else BORD, 3 if nv else 1.5, 8, None, None, cid)
        s.texte(cx + 10, n1_y + 49, [(t, T1, True, 13)], c=cid)
        s.texte(cx + 10, n1_y + 66, [(ls[0], T3, False, 12)], c=cid)
        s.texte(cx + 10, n1_y + 82, [(ls[1], T3, False, 12)], c=cid)
        if nv:
            s.pastille(cx + cw - 82, n1_y + 21)
        if i == 0:
            g["api"] = (cx, n1_y + 32, cw, 58)
        cx += cw + 10
    if cfg.get("node1_note"):
        for k, l in enumerate(cfg["node1_note"]):
            s.texte(cx + 6, n1_y + 54 + 18 * k, [(l, T3, False, 12)])
    if cfg.get("poste"):
        ax, ay, aw, ah = g["api"]
        s.fleche([(X0, rowA_y + 33), (LANE_A, rowA_y + 33), (LANE_A, ay + 46), (ax, ay + 46)], "or")

    # --- composants : Services, pods, couloirs
    for i, sl in enumerate(slots):
        sx = SLOT0 + i * W
        g["slot_x"][i] = sx
        g["c"][i] = sx + W / 2
        pl = sl["pill"]
        s.service(sx + 8, pill_top, W - 16, pl["nom"], pl.get("ip", ""), pl.get("ports", ""), nouveau=pl.get("nouveau", False),
                  pastille=True, titre=pl.get("titre", "Service "), ligne2=pl.get("ligne2"), h=pill_h,
                  dash=pl.get("dash"), stroke=pl.get("stroke"))
        g["pill"][i] = (sx + 8, pill_top, W - 16, pill_h)
        lx = sx + 14
        tg = []
        for k in (2, 3):
            lst = sl["pods"].get(k, [])
            for j, pd in enumerate(lst):
                py = band[k] + bh - 22 - ph - j * (ph + 6)
                g["podr"][(i, k, j)] = (sx + 34, py, W - 40, ph)
                draw = cfg.get("pod_draw")
                if draw:
                    draw(s, sx + 34, py, W - 40, pd, ph)
                else:
                    s.pod(sx + 34, py, W - 40, pd["n"], pd["ip"], pd.get("p"), pd.get("x"), pd.get("nouveau", False), pd.get("fantome", False),
                          h=ph, pastille=pd.get("nouveau", False) and j == len(lst) - 1)
                tg.append((py + ph / 2, pd.get("fantome", False), sx + 34))
        if tg and not sl.get("sans_couloir"):
            tg.sort()
            lc, ld = sl.get("lane_coul", "bleu"), sl.get("lane_dash")
            s.fleche([(lx, pill_top + pill_h), (lx, tg[-1][0])], lc, 2, dash=ld, ligne_seule=True)
            for yy, fant, x in tg:
                s.fleche([(lx, yy), (x, yy)], lc, 2, dash="4 3" if fant else ld)

    # --- flèches d'entrée (Ingress -> Services)
    if ing and ing != "fantome":
        rts = []
        for i, sl in enumerate(slots):
            for (txt, dx) in sl.get("routes", []):
                rts.append((g["c"][i] + dx, txt, i))
        if rts:
            xs = [r[0] for r in rts] + [g["ingx"]]
            s.fleche([(g["ingx"], rowB_bot), (g["ingx"], bus_y), (min(xs), bus_y)], "or", 2, ligne_seule=True)
            for (x, txt, i) in rts:
                s.fleche([(x, bus_y), (x, pill_top)], "or", 2)
            if num:
                s.etape(g["ingx"] + 20, (rowB_bot + bus_y) / 2, 4)
                s.etape(rts[0][0], bus_y + 21, 5)
        g["routes"] = rts
    # --- appels entre services
    for cl in cfg.get("calls", []):
        i, oi, yl = cl["i"], cl["oi"], lvl_y[cl["lvl"]]
        x0 = g["c"][i] + oi
        tgs = [(g["c"][j] + o) for (j, o) in cl["tg"]]
        far = max(tgs, key=lambda v: abs(v - x0))
        s.fleche([(x0, pill_top), (x0, yl), (far, yl), (far, pill_top)], cl.get("coul", "gris"), 2)
        for t in tgs:
            if t != far:
                s.fleche([(t, yl), (t, pill_top)], cl.get("coul", "gris"), 2)
        if cl.get("cv"):   # appel multiple : une lettre au milieu de chaque descente
            for lt, t in zip(cl["l"], tgs):
                s.appel(t, (yl + pill_top) / 2, lt)
        else:
            s.appel((x0 + tgs[0]) / 2, yl, cl["l"][0])
    # --- puces d'étape sur les couloirs
    if num:
        s.etape(g["slot_x"][0] + 14, pill_top + pill_h + 16, 6)
    # --- étiquettes de routes (en dernier pour passer au-dessus des lignes)
    if ing and ing != "fantome":
        for (x, txt, i) in g.get("routes", []):
            gauche = txt in cfg.get("route_gauche", ("/verification",))
            w = largeur(txt, 12, True) + 12
            s.chip(x - w / 2 - 8 if gauche else x + w / 2 + 8, bus_y, txt, OR_CLAIR, 12, True)
    return g


def bas(s, y, etapes=None, appels=None, titre_e="Parcours d'une requête (cercles or)", titre_a="Appels entre Services (cercles gris)",
        xe=60, xa=860, dy=21, deux_col=False):
    """Panneaux explicatifs sous le cluster."""
    if etapes:
        s.texte(xe, y, [(titre_e, OR, True, 14)])
        n1 = (len(etapes) + 1) // 2 if deux_col else len(etapes)
        for i, (num, t) in enumerate(etapes):
            col, ligne = (0, i) if i < n1 else (1, i - n1)
            ly = y + 28 + ligne * dy
            s.etape(xe + 11 + col * 740, ly - 4, num)
            s.texte(xe + 30 + col * 740, ly, [(t, T2, False, 12)])
    if appels:
        s.texte(xa, y, [(titre_a, T1, True, 14)])
        for i, (lt, t) in enumerate(appels):
            ly = y + 28 + i * dy
            s.appel(xa + 11, ly - 4, lt)
            s.texte(xa + 30, ly, [(t, T2, False, 12)])


# ================================================================ données communes de l'application
SVC = {  # IP de Services (exemples dans 10.43.0.0/16) et ports
    "front": ("10.43.88.12", "8080"), "back": ("10.43.201.5", "8000"), "qr-generator": ("10.43.17.60", "8001"),
    "qr-verifier": ("10.43.149.23", "8002"), "redis": ("10.43.62.101", "6379"), "postgres": ("10.43.230.74", "5432"),
}


def pill(nom, nouveau=False, **kw):
    ip, port = SVC[nom]
    d = dict(nom=nom, ip=ip, ports=port, nouveau=nouveau)
    d.update(kw)
    return d


def slots_app(nv=(), pg_pod=None, redis_pod=None, back_x="env : Secrets", front_x="env : API_INTERNE", pg_x="pas de volume", rd_x="sans persistance"):
    """Les six composants de l'application, dans l'ordre des colonnes ; nv = noms marqués NOUVEAU."""
    pg = pg_pod or pod_d("postgres-6f9d-l2k8m", "10.42.1.8", 5432, pg_x)
    rd = redis_pod or pod_d("redis-5b7c-t3w8z", "10.42.2.9", 6379, rd_x)
    sl = [
        dict(pill=pill("front", "front" in nv), routes=[("/", 0)],
             pods={2: [pod_d("front-6d8f7-x2k4p", "10.42.1.14", 8080, front_x), pod_d("front-6d8f7-m9q2z", "10.42.1.15", 8080, front_x)],
                   3: [pod_d("front-6d8f7-t5w8c", "10.42.2.12", 8080, front_x)]}),
        dict(pill=pill("back", "back" in nv), routes=[("/api", 0)],
             pods={2: [pod_d("back-7c5b9-h4n6r", "10.42.1.21", 8000, back_x)],
                   3: [pod_d("back-7c5b9-j8v3d", "10.42.2.23", 8000, back_x), pod_d("back-7c5b9-q2l7s", "10.42.2.24", 8000, back_x)]}),
        dict(pill=pill("qr-generator", "qr-generator" in nv), routes=[("/qr", 0)],
             pods={2: [pod_d("qr-generator-d7k2p", "10.42.1.33", 8001, "Secret cinetint-cle", "qr-generator" in nv)],
                   3: [pod_d("qr-generator-w9m4x", "10.42.2.31", 8001, "Secret cinetint-cle", "qr-generator" in nv)]}),
        dict(pill=pill("qr-verifier", "qr-verifier" in nv), routes=[("/verification", 0)],
             pods={2: [pod_d("qr-verifier-k4m8n", "10.42.1.34", 8002, "Secret cinetint-cle", "qr-verifier" in nv)],
                   3: [pod_d("qr-verifier-p6t2v", "10.42.2.32", 8002, "Secret cinetint-cle", "qr-verifier" in nv)]}),
        dict(pill=pill("redis", "redis" in nv), pods={3: [rd]}),
        dict(pill=pill("postgres", "postgres" in nv), pods={2: [pg]}),
    ]
    return sl


APPELS5 = [
    dict(l="A", i=0, oi=50, tg=[(1, -50)], lvl=1),
    dict(l="B", i=1, oi=70, tg=[(2, -50)], lvl=1),
    dict(l="D", i=3, oi=-50, tg=[(2, 50)], lvl=1),
    dict(l="C", i=3, oi=45, tg=[(1, 45)], lvl=2),
    dict(l="EF", i=1, oi=20, tg=[(4, -30), (5, -30)], lvl=3, cv=True),
]
APPELS5_TXT = [
    ("A", "front -> back : http://back:8000 (variable API_INTERNE)"),
    ("B", "back -> qr-generator : http://qr-generator:8001 (QR signé)"),
    ("C", "qr-verifier -> back : /internal/billets/{id}/utiliser"),
    ("D", "qr-verifier -> qr-generator : clé publique, une seule fois"),
    ("E", "back -> redis : verrous, compteurs, pub/sub (redis:6379)"),
    ("F", "back -> postgres : SQL (postgres:5432)"),
]
ETAPES = [
    (1, "Le DNS public renvoie 157.159.11.201 pour django.<groupe>.csc8567.luxbulb.org"),
    (2, "MetalLB annonce cette IP : le paquet arrive sur un nœud (NodePort 31324 pour le port 80)"),
    (3, "Le Service LoadBalancer (10.43.144.159) le passe à un pod du contrôleur ingress-nginx"),
    (4, "nginx applique la ressource Ingress : /api, /qr, /verification, sinon /"),
    (5, "Il vise le Service du composant (IP virtuelle 10.43.x.y, portée par aucune interface)"),
    (6, "kube-proxy (iptables) réécrit l'IP virtuelle en IP d'un pod, au hasard (DNAT)"),
    (7, "Le paquet suit le réseau des pods : cni0, veth du pod, tunnel VXLAN entre les workers"),
]


def legende_std(s, y, extra=()):
    items = [("fleche", "or", "flux principal"), ("fleche", "gris", "appel entre Services"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"),
             ("pointille", "gris", "lecture de configuration"), ("service", "bleu", "Service ClusterIP"), ("boite", "gris", "pod (IP d'exemple)"),
             ("nouveau", "or", "NOUVEAU dans ce défi")] + list(extra)
    return s.legende(60, y, items, 1480)


# ================================================================ défi 5
@defi(5, "Défi 5 : infrastructure réseau complète de CinetINT sur Kubernetes",
      "défi 5 : infrastructure complète (Ingress, 6 Services, 12 pods sur 2 workers)")
def defi5(s):
    cfg = dict(slots=slots_app(nv=("front", "back", "qr-generator", "qr-verifier")), calls=APPELS5,
               ingress=True, poste=dict(lignes=["kubectl apply -f k8s/defi5/"]), nouveau={"rules"},
               node1_note=["12 pods applicatifs, tous sur", "les workers (Nodes 2 et 3)"])
    g = cluster(s, cfg)
    y = g["frame_bot"] + 24
    bas(s, y, ETAPES, APPELS5_TXT)
    legende_std(s, y + 28 + 7 * 21 + 14)
    s.texte(60, y + 28 + 7 * 21 + 14 + 52, [("Pods front, back et base : requests 100m CPU / 100Mi, limits 200m CPU / 200Mi. Noms de pods abrégés, IP de pods et de Services données à titre d'exemple.", T3, False, 12)])
    return g




# ================================================================ défi 6 : Helm
def legende_une_ligne(s, y=1232, extra=()):
    items = [("fleche", "or", "flux principal"), ("fleche", "gris", "appel entre Services"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"),
             ("service", "bleu", "Service ClusterIP"), ("boite", "gris", "pod (IP d'exemple)"), ("nouveau", "or", "NOUVEAU dans ce défi")] + list(extra)
    s.legende(60, y, items, 1500)


@defi(6, "Défi 6 : déploiement par Helm (charte, release, ConfigMap, Secret)",
      "défi 6 : Helm, une charte, une release, ConfigMap et Secret injectés dans les pods")
def defi6(s):
    cfg = dict(slots=slots_app(back_x="ConfigMap + Secret", front_x="env : ConfigMap", pg_x="ConfigMap + Secret", rd_x="sans persistance"),
               calls=APPELS5, ingress=True, numeros=False,
               node1_note=["La release et les manifests", "passent par l'API server"])
    g = cluster(s, cfg)
    y0 = g["frame_bot"] + 18
    api = g["api"]
    # poste et charte
    s.boite(60, y0, 300, 86, "Poste du développeur", ["helm upgrade --install cinetint", "-f values-cours.yaml"], nouveau=True)
    s.fleche([(170, y0), (170, api[1] + api[3])], "or")
    s.texte(158, y0 - 6, [("manifests rendus", T2, False, 12)], ancre="end")
    s.boite(60, y0 + 112, 300, 126, "Charte Helm cinetint", ["Chart.yaml : version, dépendances", "values.yaml : tous les réglages", "templates/ : modèles des objets",
                                                          "Go templates : boucles, conditions"], nouveau=True)
    s.fleche([(210, y0 + 112), (210, y0 + 86)], "gris", dash="5 4")
    s.texte(198, y0 + 104, [("helm lit la charte", T2, False, 12)], ancre="end")
    # objets de l'espace de noms
    s.texte(400, y0 + 6, [("Objets de l'espace u-XXX (dans etcd)", T3, False, 12)])
    s.boite(400, y0 + 16, 390, 107, "ConfigMap cinetint-config", ["POSTGRES_HOST=postgres, POSTGRES_PORT=5432", "POSTGRES_DB, POSTGRES_USER", "REDIS_URL=redis://redis:6379/0"],
            nouveau=True, tsize=13)
    s.boite(400, y0 + 135, 390, 88, "Secret cinetint-secrets", ["POSTGRES_PASSWORD", "générés par la charte, jamais dans le dépôt"], nouveau=True, tsize=13)
    # zoom du pod back
    zx = 1010
    s.boite(zx, y0, 550, 168, "Pod back (zoom) : variables d'environnement",
            [[("POSTGRES_HOST, PORT, DB, USER", OR_CLAIR, True), ("  <-  configMapKeyRef", BLEU_CLAIR)],
             [("POSTGRES_PASSWORD", OR_CLAIR, True), ("  <-  secretKeyRef cinetint-secrets", BLEU_CLAIR)],
             [("REDIS_URL", OR_CLAIR, True), ("  <-  configMapKeyRef cinetint-config", BLEU_CLAIR)],
             ("DATABASE_URL, assemblée par Kubernetes avec $(VARIABLE) :", T2),
             ("postgresql+asyncpg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)", OR_CLAIR),
             ("@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)", OR_CLAIR)], tsize=13, nouveau=True)
    s.fleche([(790, y0 + 50), (zx, y0 + 50)], "bleu")
    s.chip(900, y0 + 50, "configMapKeyRef", BLEU_CLAIR)
    s.fleche([(790, y0 + 178), (880, y0 + 178), (880, y0 + 100), (zx, y0 + 100)], "bleu")
    s.chip(950, y0 + 100, "secretKeyRef", BLEU_CLAIR)
    s.boite(zx, y0 + 182, 550, 66, "Secret sh.helm.release.v1.cinetint.v1", ["historique des révisions : helm rollback"], nouveau=True, tsize=13)
    legende_une_ligne(s, y0 + 262)


# ================================================================ défi 7 : StatefulSet, PVC, Service headless
@defi(7, "Défi 7 : PostgreSQL en StatefulSet avec volume persistant et Service headless",
      "défi 7 : postgres-0 (StatefulSet), volume persistant (PVC, PV), Service headless")
def defi7(s):
    pg = pod_d("postgres-0", "10.42.1.8", 5432, "volume : data-postgres-0", nouveau=True)
    sl = slots_app(back_x="ConfigMap + Secret", front_x="env : ConfigMap", pg_pod=pg, rd_x="sans persistance")
    sl[5]["pill"] = pill("postgres", True, ligne2="headless : sans IP", dash="6 4")
    sl[5]["lane_coul"], sl[5]["lane_dash"] = "or", "6 4"
    cfg = dict(slots=sl, calls=APPELS5, ingress=True, numeros=False, poste=dict(lignes=["helm upgrade --install cinetint"]),
               node1_note=["etcd garde aussi le PVC", "et le PV (volume persistant)"])
    g = cluster(s, cfg)
    # PVC au-dessus du pod postgres-0, dans le nœud 2
    x, y, w, h = g["podr"][(5, 2, 0)]
    bid = s.nid()
    s.rect(x, y - 58, w, 44, CARTE, OR, 3, 8, None, None, bid)
    s.texte(x + 10, y - 40, [("PVC data-postgres-0", T1, True, 12)], c=bid)
    s.texte(x + 10, y - 23, [("100Mi, ReadWriteOnce", OR_CLAIR, False, 12)], c=bid)
    s.fleche([(x + w / 2, y), (x + w / 2, y - 14)], "or", 2, ligne_seule=True)
    # DNS direct vers le pod (headless)
    lx = g["slot_x"][5] + 14
    s.chip(lx + 40, g["pill_top"] + g["pill_h"] + 17, "DNS : 10.42.1.8", OR_CLAIR)
    y0 = g["frame_bot"] + 18
    # P1 : chaîne de stockage
    s.texte(60, y0 + 6, [("Stockage persistant", OR, True, 14)])
    s.boite(60, y0 + 16, 470, 64, "Pod postgres-0", ["monte /var/lib/postgresql/data (PGDATA dans pgdata)"], tsize=13, nouveau=True)
    s.fleche([(295, y0 + 80), (295, y0 + 100)], "or")
    s.boite(60, y0 + 100, 470, 64, "PVC data-postgres-0 : 100Mi", ["demande créée par le volumeClaimTemplates du StatefulSet"], tsize=13, nouveau=True)
    s.fleche([(295, y0 + 164), (295, y0 + 184)], "or")
    s.boite(60, y0 + 184, 470, 64, "PV (StorageClass par défaut)", ["créé tout seul ; il survit à la suppression du pod"], tsize=13, nouveau=True)
    # P2 : ClusterIP ou headless
    s.boite(570, y0 + 16, 500, 107, "Service ClusterIP (front, back, redis...)",
            ["1. le DNS répond l'IP virtuelle 10.43.88.12", "2. aucune interface ne porte cette IP", "3. kube-proxy la réécrit en IP de pod (DNAT)"], tsize=13, stroke=BLEU)
    s.boite(570, y0 + 135, 500, 113, "Service headless postgres (clusterIP: None)",
            ["1. le DNS répond directement l'IP du pod : 10.42.1.8", "2. connexion directe, kube-proxy hors du chemin", "3. nom par pod : postgres-0.postgres.u-XXX.svc"], tsize=13, nouveau=True)
    s.texte(570, y0 + 6, [("Deux façons de joindre une base", OR, True, 14)])
    # P3 : notes
    s.boite(1110, y0 + 16, 450, 232, "Pourquoi un StatefulSet pour la base",
            ["identité stable : toujours postgres-0", "un volume à lui, qui suit le pod", "pod supprimé : il revient avec le même volume", "données conservées (défi 5 : perdues)",
             "Deployment Recreate remplacé par un", "StatefulSet de 1 réplique, mise à jour en ordre", "le back appelle toujours « postgres »"], tsize=13, nouveau=True)
    legende_une_ligne(s, y0 + 268, extra=[("pointille", "or", "DNS direct vers le pod")])


# ================================================================ défi 8 : Rolling Update en cinq instantanés
ETATS = {
    "ready": ("Ready : reçoit le trafic", VERT, VERT, None, 1.5, 1),
    "start": ("pas Ready : sonde en cours", OR_CLAIR, OR_CLAIR, "5 4", 1.5, 1),
    "term": ("arrêt : retiré, preStop 5 s", T3, GRIS, "5 4", 1.5, 1),
    "gone": ("supprimé", GRIS, BORD, "3 3", 1.2, 0.45),
}


def pod_instantane(s, x, y, w, nom, ip, ver, etat, change, h=54):
    txt, tcol, stroke, dash, sw, op = ETATS[etat]
    bid = s.nid()
    if change:
        stroke, sw = OR, 3
    s.rect(x, y, w, h, CARTE, stroke, sw, 8, dash, op if etat == "gone" else None, bid)
    o = 0.55 if etat == "gone" else 1
    s.texte(x + 10, y + 17, [(nom, T1, True, 12), ("  " + ver, OR_CLAIR if ver == "v1" else BLEU_CLAIR, True, 12)], c=bid)
    s.texte(x + 10, y + 33, [(ip, OR_CLAIR, False, 12)], c=bid)
    s.texte(x + 10, y + 49, [(txt, tcol, False, 12)], c=bid)


@defi(8, "Défi 8 : mise à jour progressive (Rolling Update) du Deployment front",
      "défi 8 : Rolling Update du front en cinq instantanés, sans interruption", h=1230)
def defi8(s):
    # bandeau du haut : ce qui ne bouge pas
    s.boite(30, 58, 190, 72, "Navigateur", ["requêtes en continu"], tsize=14)
    s.fleche([(220, 94), (252, 94)], "or")
    s.boite(252, 58, 230, 72, "Ingress nginx", ["inchangé, /  ->  front"], tsize=14)
    s.fleche([(482, 94), (514, 94)], "or")
    s.service(514, 58, 440, "front", "10.43.88.12", "8080", h=72, ligne2="10.43.88.12 :8080  (inchangé)")
    s.boite(984, 58, 586, 72, "Deployment front : stratégie RollingUpdate", ["maxSurge 1, maxUnavailable 0, minReadySeconds 5"], tsize=13)
    s.fleche([(30, 148), (1570, 148)], "or", 2)
    s.chip(800, 148, "temps : le Service et l'Ingress ne bougent jamais", T2)

    v1 = [("front-6d8f7-x2k4p", "10.42.1.14"), ("front-6d8f7-m9q2z", "10.42.1.15"), ("front-6d8f7-t5w8c", "10.42.2.12")]
    v2 = [("front-7b2c4-h8v3n", "10.42.1.17"), ("front-7b2c4-q6d9r", "10.42.2.16"), ("front-7b2c4-w3k7s", "10.42.1.18")]
    cols = [
        dict(t="T0", titre="avant", d="3 pods v1 Ready", A=["ready", "ready", "ready"], B=[None, None, None], ra=3, rb=0,
             ep=[v1[0], v1[1], v1[2]]),
        dict(t="T1", titre="un pod v2 démarre", d="maxSurge 1, pas encore Ready", A=["ready", "ready", "ready"], B=["start", None, None], ra=3, rb=1,
             ep=[v1[0], v1[1], v1[2]]),
        dict(t="T2", titre="v2 Ready", d="un pod v1 s'arrête (preStop)", A=["ready", "ready", "term"], B=["ready", "start", None], ra=2, rb=2,
             ep=[v1[0], v1[1], v2[0]]),
        dict(t="T3", titre="même cycle", d="2 pods v2 Ready, 1 pod v1", A=["ready", "term", "gone"], B=["ready", "ready", "start"], ra=1, rb=3,
             ep=[v1[0], v2[0], v2[1]]),
        dict(t="T4", titre="fin", d="3 pods v2, ReplicaSet A à 0", A=["gone", "gone", "gone"], B=["ready", "ready", "ready"], ra=0, rb=3,
             ep=[v2[0], v2[1], v2[2]]),
    ]
    cw, gap = 300, 10
    prev = None
    ready_cnt = []
    for i, c in enumerate(cols):
        x = 30 + i * (cw + gap)
        # en-tête
        hid = s.nid()
        s.rect(x, 158, cw, 54, CARTE2, OR, 1.5, 10, None, None, hid)
        s.texte(x + 14, 180, [(c["t"], OR, True, 17), ("  " + c["titre"], T1, True, 14)], c=hid)
        s.texte(x + 14, 201, [(c["d"], T3, False, 12)], c=hid)
        # endpoints du Service
        eid = s.nid()
        s.rect(x, 220, cw, 62, "#12161a", BLEU, 1.5, 8, None, None, eid)
        s.texte(x + 12, 239, [("endpoints du Service front", BLEU_CLAIR, True, 12)], c=eid)
        s.texte(x + 12, 261, [(", ".join(ip for _, ip in c["ep"]), T1, False, 12)], c=eid)
        # ReplicaSets
        lanes = []
        for k, (cle, nom, ver, rep, ymin) in enumerate((("A", "ReplicaSet A : v1", "v1", c["ra"], 292), ("B", "ReplicaSet B : v2", "v2", c["rb"], 524))):
            rid = s.nid()
            s.rect(x, ymin, cw, 222, "#100f0b", GRIS, 1.2, 10, None, None, rid)
            s.texte(x + 34, ymin + 22, [(nom, T1, True, 13)], c=rid)
            s.texte(x + cw - 12, ymin + 22, [("replicas " + str(rep), T3, False, 12)], ancre="end", c=rid)
            etats = c[cle]
            if not any(etats):
                s.texte(x + cw / 2, ymin + 120, [("aucun pod", T3, False, 12)], ancre="middle", c=rid)
            for j, et in enumerate(etats):
                if et is None:
                    continue
                py = ymin + 38 + j * 60
                src = v1 if cle == "A" else v2
                chg = prev is not None and prev[cle][j] != et
                pod_instantane(s, x + 38, py, cw - 46, src[j][0], src[j][1], ver, et, chg)
                if et == "ready":
                    lanes.append((py + 27, "ok"))
                elif et in ("start", "term"):
                    lanes.append((py + 27, "non"))
        if lanes:
            lanes.sort()
            s.fleche([(x + 14, 282), (x + 14, lanes[-1][0])], "bleu", 2, ligne_seule=True)
            for yy, k in lanes:
                if k == "ok":
                    s.fleche([(x + 14, yy), (x + 38, yy)], "bleu", 2)
                else:
                    s.fleche([(x + 14, yy), (x + 38, yy)], "rouge", 2, dash="3 3", tete=False)
                    s.croix(x + 26, yy, ROUGE, 5)
        ready_cnt.append(sum(1 for e in c["A"] + c["B"] if e == "ready"))
        prev = c

    # courbes
    s.rect(30, 764, 1540, 150, CARTE, BORD, 1.5, 10)
    s.texte(46, 788, [("Pendant la mise à jour", T1, True, 14), ("   mesures aux cinq instants", T3, False, 12)])
    yv = lambda v: 896 - 20 * v
    for v in (0, 3, 4):
        s.ligne(150, yv(v), 1500, yv(v), "#2a2620", 1)
        s.texte(136, yv(v) + 4, [(str(v), T3, False, 12)], ancre="end")
    cx = [30 + i * 310 + 150 for i in range(5)]
    tot = [3, 4, 4, 4, 3]
    s.fleche([(cx[i], yv(tot[i])) for i in range(5)], GRIS, 2, tete=False)
    s.fleche([(cx[i], yv(ready_cnt[i])) for i in range(5)], "or", 3, tete=False)
    s.fleche([(cx[i], yv(0)) for i in range(5)], "vert", 3, tete=False)
    for i in range(5):
        s.rect(cx[i] - 5, yv(tot[i]) - 5, 10, 10, GRIS if tot[i] == 4 else OR, None, 1, 5)
        s.rect(cx[i] - 5, yv(0) - 5, 10, 10, VERT, None, 1, 5)
    s.texte(1560, yv(0) - 8, [("requêtes en erreur : 0", VERT, True, 12)], ancre="end")
    s.texte(1560, yv(3) + 24, [("pods Ready : toujours 3 (maxUnavailable 0)", OR_CLAIR, True, 12)], ancre="end")
    s.texte(cx[2] + 18, yv(4) - 8, [("pods au total : 4 pendant le remplacement (maxSurge 1)", T3, False, 12)])

    # commandes
    s.boite(30, 930, 800, 130, "Lancer et suivre la mise à jour",
            [("helm upgrade --install cinetint ./helm/cinetint --set images.tags.front=v2", OR_CLAIR),
             ("kubectl rollout status deployment/front", T2), ("kubectl rollout history deployment/front", T2),
             ("kubectl get replicaset -l app.kubernetes.io/component=front", T2)], tsize=13)
    s.boite(860, 930, 710, 130, "Revenir en arrière",
            [("kubectl rollout undo deployment/front", OR_CLAIR), ("helm rollback cinetint", OR_CLAIR),
             ("le ReplicaSet A reste à 0 pod : le retour réactive v1", T3), ("sans reconstruire l'image ni recréer l'objet", T3)], tsize=13)
    s.boite(30, 1078, 1540, 70, "Pourquoi aucune requête n'est perdue",
            ["readinessProbe /sante : un pod n'entre dans les endpoints qu'une fois Ready ; preStop sleep 5 : il en sort avant de recevoir son signal d'arrêt"], tsize=13)
    s.legende(30, 1178, [("fleche", "bleu", "Service -> pod (endpoints)"), ("pointille", "rouge", "aucun trafic (pod pas Ready ou en arrêt)"),
                         ("boite", "vert", "pod Ready"), ("nouveau", "or", "pod dont l'état change à cet instant")], 1540)


# ================================================================ défi 11 : NetworkPolicy sur postgres-0
def source_np(s, x, y, nom, ip, noeud, etiquette, ok, w=368, h=62):
    bid = s.nid()
    coul = VERT if ok else ROUGE
    s.rect(x, y, w, h, CARTE, coul, 2, 8, None, None, bid)
    s.texte(x + 12, y + 18, [(nom, T1, True, 12)], c=bid)
    s.texte(x + 12, y + 35, [(ip + "  (" + noeud + ")", OR_CLAIR, False, 12)], c=bid)
    s.texte(x + 12, y + 52, [(etiquette, VERT if ok else "#e08a7f", False, 12)], c=bid)
    return (x, y, w, h)


@defi(11, "Défi 11 : NetworkPolicy qui protège la base de données",
      "défi 11 : NetworkPolicy cinetint-postgres-acces, seul le back joint postgres-0 sur 5432", h=1100)
def defi11(s):
    s.texte(40, 132, [("Clients de PostgreSQL (port 5432)", OR, True, 14)])
    s.cadre(40, 150, 400, 424, None)
    s.texte(54, 172, [("espace de noms u-XXX (le vôtre)", GRIS, False, 12)])
    ys = [190, 262, 334, 424, 496]
    src = [
        ("back-7c5b9-j8v3d", "10.42.2.23", "Node 3", "component=back", True),
        ("back-7c5b9-q2l7s", "10.42.2.24", "Node 3", "component=back", True),
        ("back-7c5b9-h4n6r", "10.42.1.21", "Node 2", "component=back", True),
        ("front-6d8f7-x2k4p", "10.42.1.14", "Node 2", "component=front", False),
        ("test-psql", "10.42.2.40", "Node 3", "pod de test, sans component=back", False),
    ]
    for y, (n, ip, nd, et, ok) in zip(ys, src):
        source_np(s, 56, y, n, ip, nd, et, ok)
    s.cadre(40, 598, 400, 120, None)
    s.texte(54, 620, [("espace de noms u-autre (une autre équipe)", GRIS, False, 12)])
    source_np(s, 56, 632, "back-7c5b9-z4n8c", "10.42.2.77", "Node 3", "component=back, mais autre espace", False)

    # Node 2 et pare-feu
    s.cadre(520, 100, 1050, 660, None, stroke=GRIS, fill="#100f0b", dash=None)
    s.texte(536, 122, [("Node 2 (worker)", T1, True, 14), ("   pods 10.42.1.0/24", T3, False, 12)])
    s.rect(556, 140, 10, 610, OR_CLAIR, None, 1, 4, None, 0.45)
    s.texte(536, 778, [("pont cni0 (tunnel VXLAN vers Node 3)", T3, False, 12)])
    fid = s.nid()
    s.rect(600, 140, 280, 610, CARTE, OR, 3, 10, None, None, fid)
    s.pastille(800, 129)
    s.texte(614, 162, [("Filtre sur le veth", T1, True, 14)], c=fid)
    s.texte(614, 180, [("règles iptables de Canal", T3, False, 12)], c=fid)
    a = s.nid()
    s.rect(610, 192, 260, 226, "#14201a", VERT, 1.5, 8, None, None, a)
    s.texte(624, 216, [("AUTORISÉ", VERT, True, 13)], c=a)
    for i, l in enumerate(("pods de l'espace u-XXX", "avec l'étiquette component=back", "vers le port 5432/TCP", "(ingress.from + ports)")):
        s.texte(624, 240 + 20 * i, [(l, T2, False, 12)], c=a)
    d = s.nid()
    s.rect(610, 430, 260, 310, "#231512", ROUGE, 1.5, 8, None, None, d)
    s.texte(624, 454, [("REFUSÉ", "#e08a7f", True, 13)], c=d)
    for i, l in enumerate(("tout le reste, jeté sans réponse :", "le front, un pod de test,", "tout pod d'un autre espace,", "tout autre port de postgres-0")):
        s.texte(624, 478 + 20 * i, [(l, T2, False, 12)], c=d)
    # flèches des sources
    for y, ok in ((ys[0], True), (ys[1], True), (ys[2], True)):
        yy = y + 31
        s.fleche([(424, yy), (610, yy)], "vert", 2)
    s.chip(482, ys[0] + 31 - 22, "autorisé", VERT)
    for y in (ys[3], ys[4], 632):
        yy = y + 31
        s.fleche([(424, yy), (582, yy)], "rouge", 2, tete=False)
        s.croix(596, yy, ROUGE, 5)
        s.chip(482, yy - 20, "bloqué", "#e08a7f")
    # NetworkPolicy et agent
    s.boite(910, 130, 650, 152, "NetworkPolicy cinetint-postgres-acces",
            [[("podSelector", OR_CLAIR, True), ("  component=postgres  (pods protégés)", T2)],
             [("policyTypes", OR_CLAIR, True), ("  Ingress  (seule l'entrée est filtrée)", T2)],
             [("ingress.from", OR_CLAIR, True), ("  podSelector component=back", T2)],
             [("ingress.ports", OR_CLAIR, True), ("  5432/TCP", T2)]], tsize=14, nouveau=True)
    s.boite(910, 312, 650, 96, "Agent Canal (Calico, Felix) sur Node 2",
            ["lit la NetworkPolicy auprès de l'API server", "écrit les règles iptables du veth de postgres-0"], tsize=13)
    s.fleche([(1235, 282), (1235, 312)], "gris", dash="5 4")
    s.fleche([(910, 360), (880, 360)], "or")
    # pod protégé
    s.boite(960, 450, 360, 150, "Pod postgres-0 (StatefulSet)",
            [("10.42.1.8  :5432", OR_CLAIR), "component=postgres", "volume data-postgres-0 (100Mi)", "ne voit que ce que le filtre laisse passer"], tsize=13)
    s.fleche([(880, 525), (960, 525)], "vert", 3)
    s.chip(920, 505, "veth", T2)
    s.boite(910, 630, 650, 110, "Preuve par le test",
            [[("depuis un pod back : ", T2), ("psql -h postgres  ->  connexion acceptée", VERT)],
             [("depuis un pod de test : ", T2), ("psql -h postgres  ->  délai dépassé", "#e08a7f")]], tsize=13)
    # explications en bas
    s.boite(40, 810, 760, 150, "Comment la règle est appliquée",
            ["1. la NetworkPolicy est un objet de l'espace u-XXX, stocké dans etcd", "2. l'agent du CNI (Canal) sur chaque nœud la lit par l'API server",
             "3. il pose des règles iptables sur le veth du pod postgres-0", "4. un pod sélectionné par une règle refuse tout ce qui n'est pas listé",
             "5. le filtre est sur le nœud de la base : la source peut venir de n'importe lequel"], tsize=14)
    s.boite(830, 810, 740, 170, "Ce que le schéma montre",
            ["autorisé : les trois pods back (Node 2 et Node 3), étiquette component=back", "bloqué : le front, qui passe par le back et n'a pas besoin de la base",
             "bloqué : un pod de test du même espace de noms", "bloqué : un pod back d'un autre espace (même étiquette, autre espace)",
             "podSelector seul ne franchit pas les espaces : ils sont isolés", "l'Ingress et les autres Services de l'application ne changent pas"], tsize=14, nouveau=False)
    s.legende(40, 1020, [("fleche", "vert", "trafic autorisé"), ("fleche", "rouge", "trafic refusé (croix)"), ("fleche", "or", "l'agent programme le filtre"),
                         ("pointille", "gris", "lecture de l'objet"), ("nouveau", "or", "NOUVEAU : ajouté par ce défi")], 1500)
    s.texte(40, 1068, [("Suite du défi 10 : même application (front, back, qr-generator, qr-verifier, Redis, postgres-0), seule la base est désormais fermée par une règle.", T3, False, 12)])


# ================================================================ défi 12 : réplication Postgres en flux
def pod_pg(s, x, y, w, h, titre, nouveau=False):
    bid = s.nid()
    s.rect(x, y, w, h, CARTE, OR if nouveau else GRIS, 3 if nouveau else 1.5, 10, None, None, bid)
    s.texte(x + 16, y + 24, [(titre[0], T1, True, 13), ("  " + titre[1], OR_CLAIR, False, 12)], c=bid)
    return bid


def bloc_pg(s, x, y, w, h, titre, lignes, stroke=BORD, fill=CARTE2, sw=1.5, tsize=12, coul_titre=T1):
    bid = s.nid()
    s.rect(x, y, w, h, fill, stroke, sw, 8, None, None, bid)
    s.texte(x + 12, y + 19, [(titre, coul_titre, True, tsize)], c=bid)
    for i, l in enumerate(lignes):
        s.texte(x + 12, y + 38 + 18 * i, [(l, T3, False, 12)], c=bid)
    return bid


@defi(12, "Défi 12 : réplication PostgreSQL en flux entre un primaire et une réplique",
      "défi 12 : réplication en flux (WAL), primaire en lecture-écriture, réplique en lecture seule", h=1190)
def defi12(s):
    s.cadre(20, 62, 1560, 1100, None)
    s.texte(1564, 82, [("Cluster Kubernetes RKE2 : espace de noms u-XXX", GRIS, False, 12)], ancre="end")
    # clients
    s.boite(130, 96, 480, 74, "Pods back (x3)", ["écrivent sur le nom postgres : INSERT, UPDATE"], tsize=14)
    s.boite(990, 96, 480, 74, "Client psql (pod ou poste)", ["lit sur le nom postgres-lecture : SELECT"], tsize=14)
    # Services
    s.service(190, 216, 360, "postgres", "10.43.230.74", "5432", ligne2="10.43.230.74 :5432   écriture (rw)", h=46)
    s.service(1050, 216, 360, "postgres-lecture", "10.43.99.17", "5432", ligne2="10.43.99.17 :5432   lecture (ro)", h=46, nouveau=True, pastille=True)
    s.fleche([(300, 170), (300, 216)], "or")
    s.chip(300, 193, "écriture", OR_CLAIR)
    s.fleche([(1230, 170), (1230, 216)], "gris")
    s.chip(1230, 193, "lecture", T2)
    # nœuds
    for nom, cidr, x in (("Node 2 (worker)", "pods 10.42.1.0/24", 40), ("Node 3 (worker)", "pods 10.42.2.0/24", 900)):
        s.rect(x, 300, 660, 580, "#100f0b", GRIS, 1.2, 12)
        s.texte(x + 16, 322, [(nom, T1, True, 14), ("   " + cidr + "   kubelet, kube-proxy, cni0", T3, False, 12)])
    for x, nom, nv in ((56, "StatefulSet postgres-primaire (1 réplique)", False), (916, "StatefulSet postgres-replique (1 réplique)", True)):
        s.rect(x, 336, 628, 524, None, OR if nv else GRIS, 3 if nv else 1.2, 12, None if nv else "6 5")
        s.texte(x + 16, 358, [(nom, OR_CLAIR if nv else GRIS, True, 12)])
        if nv:
            s.pastille(x + 628 - 84, 325)
    # primaire
    pod_pg(s, 72, 372, 596, 290, ("Pod postgres-primaire-0", "10.42.1.8 :5432"))
    bloc_pg(s, 88, 412, 564, 56, "ConfigMap postgres-init (docker-entrypoint-initdb.d)", ["crée le rôle replicateur et ajoute la ligne pg_hba"])
    bloc_pg(s, 88, 480, 380, 170, "container postgres:17-alpine (primaire)",
            ["wal_level=replica", "max_wal_senders=5", "max_replication_slots=5", "pg_hba : host replication replicateur", "lecture et écriture"])
    bloc_pg(s, 488, 512, 164, 60, "walsender", ["envoie le WAL"], stroke=OR, sw=2.5, coul_titre=OR_CLAIR)
    bloc_pg(s, 72, 684, 596, 62, "PVC data-postgres-primaire-0 : 100Mi", ["monté dans /var/lib/postgresql/data (PGDATA : pgdata)"])
    s.service(72, 764, 596, "postgres-primaire", "", "", ligne2="DNS : postgres-primaire-0.postgres-primaire", h=46, titre="Service headless ", dash="5 4")
    # réplique
    pod_pg(s, 932, 372, 596, 290, ("Pod postgres-replique-0", "10.42.2.9 :5432"), True)
    bloc_pg(s, 948, 412, 564, 56, "initContainer copie-du-primaire : pg_basebackup -R", ["copie le primaire dans le volume, écrit standby.signal"], stroke=OR, sw=2.5)
    bloc_pg(s, 948, 512, 164, 60, "walreceiver", ["reçoit le WAL"], stroke=OR, sw=2.5, coul_titre=OR_CLAIR)
    bloc_pg(s, 1132, 480, 380, 170, "container postgres:17-alpine (réplique)",
            ["hot_standby=on", "pg_is_in_recovery() = true", "lecture seule : rejoue le WAL reçu", "réplication asynchrone", "léger retard possible"])
    bloc_pg(s, 932, 684, 596, 62, "PVC data-postgres-replique-0 : 100Mi", ["monté dans /var/lib/postgresql/data (copie du primaire)"])
    s.service(932, 764, 596, "postgres-replique", "", "", ligne2="DNS : postgres-replique-0.postgres-replique", h=46, titre="Service headless ", dash="5 4", nouveau=True)
    # Services -> pods
    s.fleche([(520, 262), (520, 372)], "bleu")
    s.fleche([(1380, 262), (1380, 372)], "bleu")
    # flux WAL
    s.fleche([(652, 552), (948, 552)], "or", 4)
    for i, (t, g_, c_) in enumerate((("flux WAL continu", True, T1), ("TCP 5432", False, T2), ("slot postgres_replique_0", False, T2),
                                      ("utilisateur replicateur", False, T2), ("asynchrone", False, OR_CLAIR))):
        s.texte(800, 590 + 19 * i, [(t, c_, g_, 12)], ancre="middle")
    # copie initiale
    s.fleche([(652, 524), (730, 524), (730, 440), (948, 440)], "gris", 2, dash="6 4")
    for i, (t, c_) in enumerate((("copie initiale", T1), ("pg_basebackup -R", T2), ("avant le démarrage", T2))):
        s.texte(800, 392 + 17 * i, [(t, c_, i == 0, 12)], ancre="middle")
    # explications
    s.boite(40, 900, 500, 168, "Rôles et lecture seule",
            ["primaire : le back y écrit (Service postgres)", "réplique : lecture seule, via postgres-lecture", "pg_is_in_recovery() = true sur la réplique",
             "asynchrone : l'écriture est validée sans attendre", "la réplique, qui peut avoir un léger retard"], tsize=14)
    s.boite(560, 900, 500, 168, "Réplication en flux",
            ["slot postgres_replique_0 : le primaire garde le WAL", "tant que la réplique ne l'a pas lu (disque limité)", "adresse du primaire pour la réplique :", "postgres-primaire-0.postgres-primaire (headless)"], tsize=14, nouveau=True)
    s.boite(1080, 900, 480, 168, "Secret postgres-secrets",
            ["POSTGRES_PASSWORD et REPLICATION_PASSWORD", "lus par les deux StatefulSets (variables d'env.)", "mots de passe jamais écrits dans le dépôt"], tsize=14)
    s.legende(40, 1100, [("fleche", "or", "flux WAL continu"), ("pointille", "gris", "copie initiale"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"),
                         ("service", "bleu", "Service ClusterIP"), ("nouveau", "or", "NOUVEAU : ajouté par ce défi")], 1500)
    s.texte(40, 1140, [("Si Node 2 tombe, la réplique garde une copie des données. IP de pods et de Services données à titre d'exemple.", T3, False, 12)])


# ================================================================ défis 3 et 4 : pod à deux conteneurs, postgres, redis, Ingress
def pod_site(s, x, y, w, pd, h):
    """Pod à deux conteneurs (front + back) ou pod simple à lignes libres."""
    bid = s.nid()
    nv = pd.get("nouveau", False)
    s.rect(x, y, w, h, CARTE, OR if nv else GRIS, 3 if nv else 1.2, 8, None, None, bid)
    s.texte(x + 10, y + 17, [(pd["n"], T1, True, 12), ("   " + pd["ip"], OR_CLAIR, False, 12)], c=bid)
    if pd.get("deux"):
        iw = (w - 30) / 2
        for k, (nom, port, l2) in enumerate((("front", "8080", "-> localhost:8000"), ("back", "8000", "-> postgres, redis"))):
            ix = x + 10 + k * (iw + 10)
            cid = s.nid()
            s.rect(ix, y + 26, iw, h - 34, CARTE2, BORD, 1.2, 6, None, None, cid)
            s.texte(ix + 8, y + 44, [("conteneur " + nom, T1, True, 12), ("  :" + port, OR_CLAIR, False, 12)], c=cid)
            s.texte(ix + 8, y + 61, [(l2, T3, False, 12)], c=cid)
    else:
        for i, l in enumerate(pd.get("lignes", [])):
            col = T3
            if isinstance(l, tuple):
                l, col = l
            s.texte(x + 10, y + 34 + 16 * i, [(l, col, False, 12)], c=bid)
    if nv and pd.get("pastille"):
        s.pastille(x + w - 82, y - 15)


def slots_site(web_ing=False):
    site = lambda n, ip: dict(n=n, ip=ip, deux=True, nouveau=True)
    sl = [
        dict(pill=dict(nom="site", ip="10.43.54.18", ports="8080, 8000", ligne2="10.43.54.18 :8080 et :8000"),
             pods={2: [site("site-6b7d9-xk2lp", "10.42.1.14"), site("site-6b7d9-m4q8z", "10.42.1.15")], 3: [site("site-6b7d9-t9w3c", "10.42.2.12")]},
             routes=[("/", -90), ("/api", 90)] if web_ing else []),
        dict(pill=pill("postgres", True),
             pods={2: [pod_d("postgres-6f9d-l2k8m", "10.42.1.8", lignes=[("écoute :5432", OR_CLAIR), "env : Secret cinetint-secrets", ("sans volume : données perdues", "#e08a7f")], nouveau=True, pastille=True)]}),
        dict(pill=pill("redis", True),
             pods={3: [pod_d("redis-5b7c-t3w8z", "10.42.2.9", lignes=[("écoute :6379", OR_CLAIR), "sans persistance", "cache, verrous, pub/sub"], nouveau=True, pastille=True)]}),
    ]
    sl[0]["pods"][2][-1]["pastille"] = True
    return sl


def corriger_pods_site(sl):
    for sx in sl:
        for k, lst in sx["pods"].items():
            for pd in lst:
                if "lignes" in pd:
                    pd["lignes"] = [(":" + pd["p"] if False else l) for l in pd["lignes"]]


CALLS34 = [dict(l="A", i=0, oi=110, tg=[(1, -60)], lvl=1), dict(l="B", i=0, oi=150, tg=[(2, -60)], lvl=2)]
APPELS34 = [("A", "site (back) -> postgres"), ("B", "site (back) -> redis")]


@defi(3, "Défi 3 : Pod à deux conteneurs, PostgreSQL et Redis, accès par kubectl proxy",
      "défi 3 : pod site (front + back), postgres, redis, ConfigMap/Secret, accès par kubectl proxy", h=1250)
def defi3(s):
    cfg = dict(slots=slots_site(), calls=CALLS34, ingress="fantome", numeros=False, pod_h=84, pod_draw=pod_site, appels_txt=APPELS34,
               poste=dict(lignes=["kubectl proxy : 127.0.0.1:8001"]),
               node1_note=["Le Secret cinetint-secrets est", "stocké dans etcd"])
    g = cluster(s, cfg)
    # couloir B : l'API server relaie vers le Service
    ax, ay, aw, ah = g["api"]
    px, py, pw, ph_ = g["pill"][0]
    s.fleche([(ax, ay + 14), (LANE_B, ay + 14), (LANE_B, py + 16), (px, py + 16)], "or")
    s.chip(166, py + 16, "proxy du Service", OR_CLAIR)
    y0 = g["frame_bot"] + 20
    s.boite(60, y0, 740, 150, "Accès par kubectl proxy (aucun Ingress pour l'instant)",
            ["curl http://127.0.0.1:8001/api/v1/namespaces/u-XXX/services/site:8080/proxy/",
             "le proxy local parle HTTPS à l'API server (:6443, Node 1, trait or)",
             "l'API server relaie vers le Service site, kube-proxy choisit un des 3 pods",
             "les deux conteneurs d'un pod partagent la même IP : front appelle localhost:8000"], tsize=14)
    s.boite(830, y0, 730, 150, "Secret cinetint-secrets", ["POSTGRES_PASSWORD, injecté en variables d'environnement",
                                                          "dans les conteneurs back et postgres (secretKeyRef)",
                                                          "postgres sans volume : si le pod est recréé, les données sont perdues"], tsize=14, nouveau=True)
    legende_une_ligne(s, y0 + 180, extra=[("pointille", "gris", "Service -> pod")]) if False else s.legende(60, y0 + 184, [
        ("fleche", "or", "flux principal"), ("fleche", "gris", "appel entre Services"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"),
        ("service", "bleu", "Service ClusterIP"), ("boite", "gris", "pod (IP d'exemple)"), ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)


ETAPES4 = [
    (1, "Le DNS public renvoie 157.159.11.201 pour django.<groupe>.csc8567.luxbulb.org"),
    (2, "MetalLB annonce cette IP : le paquet arrive sur un nœud (NodePort 31324 pour le port 80)"),
    (3, "Le Service LoadBalancer (10.43.144.159) le passe à un pod du contrôleur ingress-nginx"),
    (4, "nginx applique l'Ingress site : /api vers le port 8000, le reste vers le port 8080"),
    (5, "Il vise le Service site (IP virtuelle 10.43.54.18, ports 8080 et 8000)"),
    (6, "kube-proxy (iptables) réécrit l'IP virtuelle en IP d'un des 3 pods, au hasard (DNAT)"),
    (7, "Le paquet suit le réseau des pods : cni0, veth du pod, tunnel VXLAN entre les workers"),
]


@defi(4, "Défi 4 : exposition sur Internet par MetalLB et un Ingress",
      "défi 4 : du navigateur au pod par DNS, MetalLB, Service LoadBalancer et Ingress", h=1250)
def defi4(s):
    cfg = dict(slots=slots_site(True), calls=CALLS34, ingress=True, pod_h=84, pod_draw=pod_site, appels_txt=APPELS34,
               poste=dict(lignes=["kubectl apply -f k8s/defi4/"]),
               rules_titre="Ingress site", rules=["/api -> site:8000 (back)", "/ -> site:8080 (front)"],
               nouveau={"browser", "dns", "metallb", "svclb", "ingctrl", "rules"})
    for sx in cfg["slots"]:
        for lst in sx["pods"].values():
            for pd in lst:
                pd["nouveau"] = False
                pd["pastille"] = False
    g = cluster(s, cfg)
    y0 = g["frame_bot"] + 20
    bas(s, y0, ETAPES4, deux_col=True)
    s.legende(60, y0 + 116, [("fleche", "or", "flux principal"), ("fleche", "gris", "appel entre Services"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"),
                                          ("service", "bleu", "Service ClusterIP"), ("boite", "gris", "pod (IP d'exemple)"), ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)
    s.texte(60, y0 + 152, [("Suite du défi 3 : le site est maintenant joignable depuis Internet sans kubectl ; l'application et ses 3 Services ne changent pas.", T3, False, 12)])


# ================================================================ défi 9 : autoscaling (HPA)
@defi(9, "Défi 9 : mise à l'échelle automatique du front et du back (HPA)",
      "défi 9 : metrics-server, HorizontalPodAutoscaler, de 3 à 10 pods selon le CPU", h=930)
def defi9(s):
    # chaîne de mesure
    s.boite(40, 70, 280, 84, "kubelet Node 2", ["cAdvisor : CPU de chaque conteneur"], tsize=14)
    s.boite(40, 170, 280, 84, "kubelet Node 3", ["cAdvisor : CPU de chaque conteneur"], tsize=14)
    s.boite(360, 70, 300, 92, "metrics-server", ["interroge les kubelets, 15 s", "garde les dernières mesures"], droite="kube-system", tsize=14, nouveau=True)
    s.boite(360, 186, 300, 92, "API metrics.k8s.io", ["servie par l'API server", "kubectl top pods lit ici"], tsize=14, nouveau=True)
    s.boite(700, 70, 300, 168, "Contrôleur HPA", ["boucle toutes les 15 secondes", "désiré = ceil(actuel x usage / cible)", "exemple : 3 pods à 150 % du CPU",
                                                   "ceil(3 x 150 / 60) = 8 pods", "borné entre min 3 et max 10"], droite="controller-manager", tsize=14, nouveau=True)
    s.fleche([(320, 112), (360, 112)], "gris")
    s.fleche([(320, 212), (340, 212), (340, 124), (360, 124)], "gris")
    s.etape(340, 92, 1)
    s.fleche([(510, 162), (510, 186)], "gris")
    s.etape(534, 174, 2)
    s.fleche([(660, 224), (700, 224)], "gris")
    s.etape(680, 206, 3)
    # HPA objets
    s.boite(700, 330, 300, 150, "HPA front", ["cible : 60 % du CPU demandé", "= 60m (requests 100m)", "minReplicas 3, maxReplicas 10", "scaleTargetRef : Deployment front"], tsize=14, nouveau=True)
    s.boite(700, 590, 300, 150, "HPA back", ["cible : 60 % du CPU demandé", "= 60m (requests 100m)", "minReplicas 3, maxReplicas 10", "scaleTargetRef : Deployment back"], tsize=14, nouveau=True)
    s.fleche([(850, 238), (850, 330)], "gris")
    s.etape(872, 284, 4)
    s.fleche([(720, 238), (720, 262), (682, 262), (682, 665), (700, 665)], "gris")
    s.fleche([(1000, 380), (1040, 380)], "gris", dash="5 4")
    s.fleche([(1000, 640), (1040, 640)], "gris", dash="5 4")
    s.fleche([(1000, 150), (1022, 150), (1022, 480), (1040, 480)], "or")
    s.fleche([(1022, 480), (1022, 740), (1040, 740)], "or")
    # générateur de charge et entrée
    s.boite(1040, 70, 250, 84, "Générateur de charge", ["boucle de requêtes (hey, curl)"], tsize=14)
    s.fleche([(1290, 112), (1320, 112)], "or")
    s.boite(1320, 70, 240, 84, "Ingress puis Services", ["/ : front   /api : back"], tsize=14)
    # groupes de pods
    for nom, y, cible in (("front", 330, 8), ("back", 590, 8)):
        gid = s.nid()
        s.rect(1040, y, 520, 220 if nom == "front" else 150 + 70, CARTE, GRIS, 1.5, 10, None, None, gid)
        s.texte(1056, y + 24, [("Deployment " + nom, T1, True, 14)], c=gid)
        s.texte(1544, y + 24, [("replicas 3  ->  jusqu'à 10", OR_CLAIR, False, 12)], ancre="end", c=gid)
        for k in range(10):
            col, lig = k % 5, k // 5
            px, py = 1054 + col * 100, y + 42 + lig * 62
            fant = k >= 3
            pid = s.nid()
            s.rect(px, py, 92, 54, CARTE2, GRIS if fant else OR, 1.2 if fant else 2, 7, "4 3" if fant else None, 0.55 if fant else None, pid)
            s.texte(px + 8, py + 20, [("%s #%d" % (nom, k + 1), T1, True, 12)], c=pid)
            s.texte(px + 8, py + 38, [("150m" if not fant else "ajouté", OR_CLAIR if not fant else T3, False, 12)], c=pid)
        s.texte(1056, y + 42 + 2 * 62 + 14, [("3 pods en service, 7 emplacements ajoutés si la charge monte", T3, False, 12)], c=gid)
    s.fleche([(1440, 154), (1440, 330)], "or")
    s.chip(1440, 242, "requêtes", T2)
    s.fleche([(1560, 112), (1580, 112), (1580, 700), (1560, 700)], "or")
    s.etape(1022, 300, 5)
    s.etape(1060, 330 + 24 + 0, 6) if False else None
    # explications
    s.boite(40, 310, 620, 224, "Boucle de régulation (toutes les 15 secondes)",
            [[("1  ", OR, True), ("kubelet : cAdvisor mesure le CPU de chaque conteneur de son nœud", T2)],
             [("2  ", OR, True), ("metrics-server collecte ces mesures auprès des kubelets", T2)],
             [("3  ", OR, True), ("il les publie par l'API metrics.k8s.io (agrégée par l'API server)", T2)],
             [("4  ", OR, True), ("le contrôleur HPA les lit et compare à la cible : 60 % du CPU demandé", T2)],
             [("5  ", OR, True), ("trop haut : il écrit un replicas plus grand dans le Deployment", T2)],
             [("6  ", OR, True), ("le ReplicaSet crée les pods (pointillés), le Service les ajoute une fois Ready", T2)]], tsize=14)
    s.boite(40, 556, 620, 224, "Ce qui est réglé",
            ["cible 60 % : le CPU demandé vaut 100m, donc 60m par pod", "minimum 3 pods : la capacité de départ ne baisse jamais",
             "maximum 10 pods : plafond de ressources du cluster", "le même calcul vaut pour le front et pour le back",
             "retour à 3 pods quand la charge retombe (après 5 min)", "les pods ajoutés vont sur Node 2 ou Node 3 (scheduler)"], tsize=14)
    s.legende(40, 846, [("fleche", "or", "flux principal"), ("fleche", "gris", "mesure ou lecture"), ("boite", "or", "pod existant"),
                         ("fantome", "gris", "pod ajouté si la charge monte"), ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)
    s.texte(40, 892, [("Suite du défi 8 : même application. Exemple chiffré, les valeurs réelles dépendent de la charge envoyée.", T3, False, 12)])


# ================================================================ défi 10 : sondes
def pod_lignes(s, x, y, w, pd, h):
    bid = s.nid()
    nv = pd.get("nouveau", False)
    s.rect(x, y, w, h, CARTE, OR if nv else GRIS, 3 if nv else 1.2, 8, None, 0.55 if pd.get("fantome") else None, bid)
    s.texte(x + 10, y + 17, [(pd["n"], T1, True, 12)], c=bid)
    s.texte(x + 10, y + 33, [("%s  :%s" % (pd["ip"], pd["p"]), OR_CLAIR, False, 12)], c=bid)
    for i, l in enumerate(pd.get("lignes", [])):
        col = T3
        if isinstance(l, tuple):
            l, col = l
        s.texte(x + 10, y + 49 + 16 * i, [(l, col, False, 12)], c=bid)
    if nv and pd.get("pastille"):
        s.pastille(x + w - 82, y - 11)


SONDES = {  # composant : (ligne 1, ligne 2)
    "front": ("R L : httpGet", "/sante :8080"),
    "back": ("S R : /api/sante", "L : /api/docs"),
    "qr-generator": ("R L : httpGet", "/qr/sante :8001"),
    "qr-verifier": ("R L : httpGet", "/verification/sante"),
    "redis": ("R L : exec", "redis-cli ping"),
    "postgres": ("S R L : exec", "pg_isready"),
}


@defi(10, "Défi 10 : sondes de démarrage, de disponibilité et de vie",
      "défi 10 : le kubelet teste chaque conteneur (startup, readiness, liveness)", h=1250)
def defi10(s):
    sl = slots_app(back_x="x", front_x="x")
    for sx in sl:
        nom = sx["pill"]["nom"]
        for lst in sx["pods"].values():
            for pd in lst:
                pd["lignes"] = list(SONDES[nom])
                pd["nouveau"] = False
    cfg = dict(slots=sl, calls=APPELS5, ingress=True, numeros=False, pod_h=76, pod_draw=pod_lignes, poste=dict(lignes=["helm upgrade --install cinetint"]),
               node_lines=("pods : %s", "kubelet : lance les sondes", "kube-proxy (iptables)", "pont cni0, veth par pod"),
               node1_note=["HPA du défi 9 inchangé", "(non redessiné ici)"])
    g = cluster(s, cfg)
    y0 = g["frame_bot"] + 18
    # trois sondes, trois effets
    s.texte(60, y0 + 4, [("Trois sondes, trois effets", OR, True, 14)])
    rows = [("S", BLEU, "startup (démarrage)", "tant qu'elle échoue, les deux autres attendent : un démarrage lent est toléré"),
            ("R", OR, "readiness (prête)", "échec : le pod est retiré des endpoints du Service, sans être redémarré"),
            ("L", ROUGE, "liveness (vivante)", "échec : le kubelet redémarre le conteneur")]
    for i, (lt, coul, nom, txt) in enumerate(rows):
        yy = y0 + 28 + i * 52
        bid = s.nid()
        s.rect(60, yy, 720, 44, CARTE, coul, 1.5, 8, None, None, bid)
        s.cercle(84, yy + 22, lt, coul, FOND, r=12)
        s.texte(106, yy + 18, [(nom, T1, True, 13)], c=bid)
        s.texte(106, yy + 35, [(txt, T2, False, 12)], c=bid)
    # cas base arrêtée
    s.texte(820, y0 + 4, [("Cas : la base est arrêtée", OR, True, 14)])
    s.boite(820, y0 + 22, 200, 78, "postgres arrêté", ["connexion refusée", "sur :5432"], stroke=ROUGE, tsize=13)
    s.fleche([(1020, y0 + 61), (1060, y0 + 61)], "rouge")
    s.boite(1060, y0 + 22, 250, 78, "pod back : pas Ready", ["R : /api/sante échoue", "(elle teste la base)"], stroke=ROUGE, tsize=13)
    s.fleche([(1310, y0 + 61), (1350, y0 + 61)], "rouge")
    s.boite(1350, y0 + 22, 210, 78, "Service back", ["ce pod est retiré,", "les autres servent"], stroke=BLEU, tsize=13)
    s.boite(1060, y0 + 114, 500, 66, "liveness /api/docs : répond", ["le conteneur est sain, il n'est donc pas redémarré"], stroke=VERT, tsize=13)
    s.fleche([(1185, y0 + 100), (1185, y0 + 114)], "vert")
    s.legende(60, y0 + 206, [("fleche", "or", "flux principal"), ("fleche", "gris", "appel entre Services"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"),
                              ("boite", "gris", "pod : S startup, R readiness, L liveness")], 1500)


# ================================================================ défis 1 et 2 : premiers pods, kubectl
def carte(s, x, y, w, h, titre, lignes, stroke=BORD, fill=CARTE2, nouveau=False, tsize=13):
    cid = s.nid()
    s.rect(x, y, w, h, fill, OR if nouveau else stroke, 3 if nouveau else 1.5, 8, None, None, cid)
    s.texte(x + 10, y + 18, [(titre, T1, True, tsize)], c=cid)
    for i, l in enumerate(lignes):
        s.texte(x + 10, y + 36 + 17 * i, [(l, T3, False, 12)], c=cid)
    if nouveau:
        s.pastille(x + w - 84, y - 11)
    return cid


@defi(1, "Défi 1 : premier Pod accessible par kubectl port-forward",
      "défi 1 : un Deployment, un ReplicaSet, un Pod, et un tunnel kubectl port-forward", h=1130)
def defi1(s):
    # poste
    s.cadre(40, 100, 380, 500, None)
    s.texte(56, 122, [("Poste du développeur (hors du cluster)", GRIS, False, 12)])
    s.boite(56, 140, 348, 140, "Terminal 1 : kubectl", ["kubectl create deployment csc8567", "  --image=xhelozs/csc8567:v1 -n u-XXX", "kubectl port-forward pods/csc8567-xxxx", "  8080:5000 -n u-XXX"], tsize=14)
    s.boite(56, 330, 348, 96, "Processus kubectl port-forward", ["écoute 127.0.0.1:8080", "relaie chaque connexion dans le tunnel"], tsize=14, nouveau=True)
    s.boite(56, 480, 348, 84, "Navigateur ou curl", ["http://localhost:8080/"], tsize=14)
    s.fleche([(230, 280), (230, 330)], "gris", dash="5 4")
    s.fleche([(230, 480), (230, 426)], "or")
    s.etape(256, 453, 1)
    # cluster
    s.cadre(460, 100, 1110, 820, None)
    s.texte(1554, 122, [("Cluster Kubernetes RKE2, espace de noms u-XXX", GRIS, False, 12)], ancre="end")
    s.rect(480, 130, 440, 770, "#100f0b", GRIS, 1.2, 12)
    s.texte(496, 154, [("Node 1 (master, control plane)", T1, True, 14)])
    s.boite(500, 172, 400, 122, "API server", [":6443 HTTPS (kubeconfig, certificat)", "authentifie, autorise, valide", "écrit dans etcd, relaie le tunnel"], tsize=14, stroke=OR)
    carte(s, 500, 306, 400, 56, "etcd :2379", ["base clé-valeur : l'état de tout le cluster"])
    carte(s, 500, 374, 400, 56, "scheduler", ["choisit le nœud de chaque nouveau pod"])
    carte(s, 500, 442, 400, 56, "controller-manager", ["boucles : Deployment, ReplicaSet, Pod..."])
    s.cadre(496, 514, 408, 372, None, stroke=GRIS)
    s.texte(510, 536, [("Objets créés par kubectl create deployment", T3, False, 12)])
    carte(s, 512, 552, 384, 60, "Deployment csc8567", ["replicas 1, image xhelozs/csc8567:v1"], nouveau=True)
    s.fleche([(704, 612), (704, 662)], "gris")
    s.texte(720, 642, [("controller-manager", T3, False, 12)])
    carte(s, 512, 662, 384, 60, "ReplicaSet csc8567-6c9d5", ["garde 1 pod en vie"], nouveau=True)
    s.fleche([(704, 722), (704, 772)], "gris")
    s.texte(720, 752, [("scheduler : Node 2", T3, False, 12)])
    carte(s, 512, 772, 384, 60, "Pod csc8567-6c9d5-x2k4p", ["créé, puis placé sur Node 2"], nouveau=True)
    # Node 2
    s.rect(1000, 130, 560, 770, "#100f0b", GRIS, 1.2, 12)
    s.texte(1016, 154, [("Node 2 (worker)", T1, True, 14), ("   pods 10.42.1.0/24", T3, False, 12)])
    s.boite(1020, 172, 520, 122, "kubelet", ["lance les conteneurs (containerd)", "ouvre le flux du port-forward vers le pod", "voit le nouveau pod en surveillant l'API server"], droite=":10250", tsize=14, stroke=OR)
    pid = s.nid()
    s.rect(1020, 340, 520, 270, CARTE, GRIS, 1.5, 10, None, None, pid)
    s.texte(1036, 364, [("Pod csc8567-6c9d5-x2k4p", T1, True, 14), ("   10.42.1.14", OR_CLAIR, False, 12)], c=pid)
    carte(s, 1036, 384, 488, 78, "espace de noms réseau du pod", ["une seule IP : 10.42.1.14", "127.0.0.1 désigne le pod lui-même"], stroke=OR)
    carte(s, 1036, 482, 488, 100, "conteneur Flask", ["image xhelozs/csc8567:v1", "écoute sur le port 5000", "sans requests ni limits (défi 1)"], stroke=OR)
    s.rect(1020, 650, 520, 10, OR_CLAIR, None, 1, 4, None, 0.45)
    s.texte(1030, 686, [("pont cni0 : le pod y est branché par une paire veth", T3, False, 12)])
    # flèches du tunnel
    s.fleche([(404, 378), (440, 378), (440, 232), (500, 232)], "or", 3)
    s.etape(440, 306, 2)
    s.fleche([(900, 232), (1020, 232)], "or", 3)
    s.etape(960, 212, 3)
    s.fleche([(1420, 294), (1420, 384)], "or", 3)
    s.etape(1446, 330, 4)
    s.fleche([(896, 802), (960, 802), (960, 272), (1020, 272)], "gris", dash="5 4")
    # explications
    s.boite(40, 940, 760, 126, "Le tunnel pas à pas",
            [[("1  ", OR, True), ("curl parle à 127.0.0.1:8080, où kubectl écoute", T2)],
             [("2  ", OR, True), ("kubectl ouvre un flux HTTPS vers l'API server (:6443, Node 1)", T2)],
             [("3  ", OR, True), ("l'API server le relaie au kubelet du nœud qui porte le pod (:10250)", T2)],
             [("4  ", OR, True), ("le kubelet se connecte au port 5000 dans l'espace réseau du pod", T2)]], tsize=14)
    s.boite(830, 940, 730, 126, "À retenir",
            ["pas de Service ni d'Ingress : c'est un accès de test", "le trafic passe par l'API server, pas par le réseau des pods",
             "un seul pod : supprimé, il revient avec une autre IP et il faut relancer le tunnel"], tsize=14)
    s.legende(40, 1096, [("fleche", "or", "flux du tunnel"), ("pointille", "gris", "le kubelet observe l'API server"), ("nouveau", "or", "NOUVEAU : créé par ce défi")], 1500)


@defi(2, "Défi 2 : Deployment à trois répliques, Service ClusterIP et kubectl proxy",
      "défi 2 : trois pods, un Service ClusterIP, un nom DNS, accès par kubectl proxy", h=1180)
def defi2(s):
    s.boite(60, 64, 480, 66, "Poste du développeur", ["kubectl proxy : écoute 127.0.0.1:8001"], tsize=14)
    s.boite(580, 64, 980, 66, "curl ou navigateur", ["http://127.0.0.1:8001/api/v1/namespaces/u-XXX/services/csc8567/proxy/"], tsize=14)
    s.fleche([(580, 97), (540, 97)], "or")
    s.etape(560, 78, 1)
    s.cadre(20, 148, 1560, 1000, None)
    s.texte(1564, 168, [("Cluster Kubernetes RKE2, espace de noms u-XXX", GRIS, False, 12)], ancre="end")
    # Node 1
    s.rect(60, 182, 1500, 150, "#100f0b", GRIS, 1.2, 12)
    s.texte(76, 206, [("Node 1 (master, control plane)", T1, True, 14), ("   aucun pod applicatif ici", T3, False, 12)])
    s.boite(76, 222, 330, 98, "API server :6443", ["reçoit l'URL de kubectl proxy", "lit le Service et ses endpoints", "relaie vers un des pods"], tsize=14, stroke=OR)
    carte(s, 420, 222, 190, 98, "etcd", ["Deployment,", "Service, endpoints"])
    carte(s, 624, 222, 190, 98, "scheduler", ["répartit les 3 pods", "sur Node 2 et Node 3"])
    carte(s, 828, 222, 230, 98, "controller-manager", ["Deployment -> ReplicaSet", "ReplicaSet -> pods"])
    s.boite(1072, 222, 474, 98, "Deployment csc8567", ["replicas 3, image xhelozs/csc8567:v1", "requests 100m / 100Mi, limits 200m / 200Mi", "ReplicaSet csc8567-6c9d5 : garde 3 pods"], tsize=14, nouveau=True)
    s.fleche([(60 + 0, 97 + 0), (LANE_A, 97)], "or", 3, tete=False, ligne_seule=True) if False else None
    s.fleche([(60, 97), (LANE_A, 97), (LANE_A, 270), (76, 270)], "or", 3)
    s.etape(LANE_A, 190, 2)
    # Service
    s.boite(640, 372, 600, 124, "Service csc8567 (ClusterIP)", ["10.43.171.20 :80  ->  pods :5000", "DNS : csc8567.u-XXX.svc.cluster.local (CoreDNS)",
                                                              "sélecteur app=csc8567 : trois endpoints"], tsize=14, stroke=BLEU, fill="#12161a", nouveau=True)
    s.texte(76, 400, [("Réseau des Services", BLEU_CLAIR, True, 13)])
    s.texte(76, 418, [("10.43.0.0/16", BLEU_CLAIR, False, 12)])
    s.fleche([(240, 320), (240, 434), (640, 434)], "or", 3)
    s.chip(440, 434, "proxy du Service", OR_CLAIR)
    s.etape(240, 380, 3)
    # nœuds
    s.rect(60, 540, 740, 340, "#100f0b", GRIS, 1.2, 12)
    s.rect(840, 540, 720, 340, "#100f0b", GRIS, 1.2, 12)
    s.texte(76, 564, [("Node 2 (worker)", T1, True, 14), ("   pods 10.42.1.0/24   kubelet, cni0", T3, False, 12)])
    s.texte(856, 564, [("Node 3 (worker)", T1, True, 14), ("   pods 10.42.2.0/24   kubelet, cni0", T3, False, 12)])
    s.boite(76, 580, 708, 82, "kube-proxy (règles iptables)", ["10.43.171.20:80 : DNAT vers l'un des 3 pods, au hasard (clients du cluster)"], tsize=13)
    s.boite(856, 580, 688, 82, "kube-proxy (règles iptables)", ["même règle sur chaque nœud : le pod appelant n'a rien à choisir"], tsize=13)
    pods = [(76, "csc8567-6c9d5-x2k4p", "10.42.1.14"), (440, "csc8567-6c9d5-m9q2z", "10.42.1.15"), (856, "csc8567-6c9d5-t5w8c", "10.42.2.12")]
    for x, nom, ip in pods:
        s.pod(x, 730, 344, nom, ip, 5000, None, True, h=96)
        s.texte(x + 10, 730 + 69, [("requests 100m / 100Mi", T3, False, 12)])
        s.texte(x + 10, 730 + 86, [("limits 200m / 200Mi", T3, False, 12)])
    s.rect(76, 856, 708, 10, OR_CLAIR, None, 1, 4, None, 0.45)
    s.rect(856, 856, 688, 10, OR_CLAIR, None, 1, 4, None, 0.45)
    # bus : l'API server choisit un endpoint
    s.fleche([(820, 496), (820, 696), (248, 696), (248, 730)], "or", 3)
    s.fleche([(820, 696), (612, 696), (612, 730)], "or", 3)
    s.fleche([(820, 696), (1028, 696), (1028, 730)], "or", 3)
    s.chip(820, 620, "l'API server choisit un endpoint", OR_CLAIR) if False else None
    s.etape(820, 596, 4)
    # explications
    s.boite(60, 900, 740, 170, "Accès par kubectl proxy",
            [[("1  ", OR, True), ("curl parle HTTP à kubectl proxy (127.0.0.1:8001)", T2)],
             [("2  ", OR, True), ("kubectl proxy transmet à l'API server (:6443, Node 1)", T2)],
             [("3  ", OR, True), ("l'API server lit le Service csc8567 : nom DNS, port 80, sélecteur", T2)],
             [("4  ", OR, True), ("il choisit l'un des trois endpoints et appelle le pod (port 5000)", T2)]], tsize=14)
    s.boite(830, 900, 730, 170, "Ce que ce défi ajoute au défi 1",
            ["trois pods au lieu d'un, répartis sur les deux workers", "chaque pod borné : requests 100m / 100Mi, limits 200m / 200Mi",
             "un Service ClusterIP : une IP virtuelle stable et un nom DNS", "le Deployment recrée un pod supprimé (autoguérison)"], tsize=14, nouveau=True)
    s.legende(60, 1100, [("fleche", "or", "chemin de la requête"), ("service", "bleu", "Service ClusterIP"), ("boite", "gris", "pod (IP d'exemple)"), ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)


# ================================================================ défi 13 : réplication dans une sous-charte Helm
@defi(13, "Défi 13 : la réplication PostgreSQL dans une sous-charte Helm",
      "défi 13 : charte cinetint, sous-charte postgres-replication, activée par une option", h=1060)
def defi13(s):
    s.boite(40, 70, 420, 90, "Poste du développeur", ["helm upgrade --install cinetint", "-f values-cours.yaml -f values-defi13.yaml"], tsize=14)
    s.boite(40, 196, 420, 150, "values-defi13.yaml",
            [("postgres-replication:", OR_CLAIR, True), ("  enabled: true", VERT), ("postgres:", OR_CLAIR, True), ("  mode: statefulset", T2)], tsize=14, nouveau=True)
    s.fleche([(250, 160), (250, 196)], "gris", dash="5 4")
    s.boite(40, 396, 420, 112, "Rendu par helm (sur le poste)", ["assemble la charte et sa sous-charte", "remplace les valeurs dans les modèles", "évalue condition: postgres-replication.enabled"], tsize=14)
    s.fleche([(250, 346), (250, 396)], "or")
    s.boite(40, 560, 420, 100, "API server (Node 1)", ["reçoit les manifests rendus", "crée les objets dans l'espace u-XXX"], tsize=14)
    s.fleche([(250, 508), (250, 560)], "or")
    s.fleche([(460, 610), (500, 610)], "or")
    # charte globale
    s.cadre(500, 70, 1060, 760, None, stroke=OR, dash=None, sw=1.5)
    s.texte(520, 94, [("charte cinetint (charte globale)", OR, True, 14)])
    s.boite(520, 110, 1020, 92, "Chart.yaml de la charte globale", [[("dependencies : ", OR_CLAIR, True), ("postgres-replication 0.1.0", T2)], [("condition : ", OR_CLAIR, True), ("postgres-replication.enabled", T2)]], tsize=14)
    carte(s, 520, 222, 320, 90, "templates/back.yaml", ["Deployment back x3 (charte parent)", "appelle le nom postgres:5432"])
    carte(s, 860, 222, 320, 90, "templates/front, qr-*, redis", ["Deployments et Services", "de la charte parent"])
    cid = s.nid()
    s.rect(1200, 222, 340, 90, CARTE2, GRIS, 1.5, 8, "5 4", 0.6, cid)
    s.texte(1210, 240, [("templates/postgres.yaml", T1, True, 13)], c=cid)
    s.texte(1210, 276, [("StatefulSet unique (défi 7)", T3, False, 12)], c=cid)
    s.texte(1210, 293, [("non rendu : la condition est vraie", T3, False, 12)], c=cid)
    # sous-charte
    s.rect(520, 340, 1020, 480, None, OR, 3, 12)
    s.pastille(1420, 329)
    s.texte(1520, 364, [("sous-charte postgres-replication (charts/postgres-replication)", OR_CLAIR, True, 13)], ancre="end")
    xs = [536, 782, 1028, 1274]
    s.service(xs[0], 384, 236, "postgres", "10.43.230.74", "5432", ligne2="10.43.230.74 :5432  rw")
    s.service(xs[1], 384, 236, "postgres-primaire", "", "", titre="headless ", ligne2="DNS par pod", dash="5 4")
    s.service(xs[2], 384, 236, "postgres-replique", "", "", titre="headless ", ligne2="DNS par pod", dash="5 4")
    s.service(xs[3], 384, 236, "postgres-lecture", "10.43.99.17", "5432", ligne2="10.43.99.17 :5432  ro")
    pid = s.nid()
    s.rect(536, 476, 440, 170, CARTE, GRIS, 1.5, 10, None, None, pid)
    s.texte(550, 500, [("StatefulSet postgres-primaire", T1, True, 13)], c=pid)
    for i, l in enumerate(("templates/primaire.yaml", "pod postgres-primaire-0 : 10.42.1.8", "PVC data-postgres-primaire-0 (100Mi)", "walsender, lecture et écriture")):
        s.texte(550, 524 + 19 * i, [(l, T3 if i else OR_CLAIR, False, 12)], c=pid)
    rid = s.nid()
    s.rect(1070, 476, 440, 170, CARTE, GRIS, 1.5, 10, None, None, rid)
    s.texte(1084, 500, [("StatefulSet postgres-replique", T1, True, 13)], c=rid)
    for i, l in enumerate(("templates/replique.yaml", "initContainer : pg_basebackup -R", "pod postgres-replique-0 : 10.42.2.9", "PVC data-postgres-replique-0 (100Mi)", "walreceiver, lecture seule")):
        s.texte(1084, 524 + 19 * i, [(l, T3 if i else OR_CLAIR, False, 12)], c=rid)
    s.fleche([(976, 590), (1070, 590)], "or", 4)
    s.chip(1023, 566, "flux WAL", OR_CLAIR)
    s.fleche([(654, 430), (654, 476)], "bleu")
    s.fleche([(1392, 430), (1392, 476)], "bleu")
    carte(s, 536, 670, 320, 66, "templates/secret.yaml", ["Secret postgres-secrets"])
    carte(s, 876, 670, 320, 66, "templates/configmap-init.yaml", ["ConfigMap postgres-init"])
    carte(s, 1216, 670, 294, 66, "templates/services.yaml", ["les quatre Services"])
    s.texte(536, 780, [("Mêmes ressources, même topologie et même flux WAL qu'au défi 12 (voir son schéma).", T3, False, 12)])
    # le back parent appelle le service de la sous-charte
    s.fleche([(654, 312), (654, 384)], "or", 3)
    s.chip(740, 350, "nom DNS : postgres", OR_CLAIR)
    s.boite(40, 860, 760, 120, "Ce que fait l'option postgres-replication.enabled",
            ["false : templates/postgres.yaml rend le StatefulSet unique du défi 7", "true : la sous-charte rend primaire et réplique, le modèle unique disparaît",
             "dans les deux cas le back appelle le même nom : postgres"], tsize=14)
    s.boite(830, 860, 730, 120, "Pourquoi une sous-charte",
            ["une unité réutilisable : ses modèles et ses valeurs sont à part", "activée par une option, sans toucher aux modèles du back",
             "le back (charte parent) ne sait pas quelle base se cache derrière"], tsize=14, nouveau=True)
    s.legende(40, 1020, [("fleche", "or", "flux principal"), ("fleche", "bleu", "Service -> pod (DNAT kube-proxy)"), ("service", "bleu", "Service ClusterIP"),
                         ("fantome", "gris", "modèle non rendu"), ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)


# ================================================================ défi 14 : rôle de Redis
@defi(14, "Défi 14 : Redis, verrous de sièges, compteurs et diffusion en direct",
      "défi 14 : un Redis, trois usages (verrous, compteurs, pub/sub), plan de salle en direct par SSE", h=1000)
def defi14(s):
    s.boite(40, 100, 260, 150, "Navigateur A", ["plan de salle de la séance", "EventSource : flux SSE"], tsize=14)
    s.boite(40, 290, 260, 150, "Navigateur B", ["un autre spectateur", "reçoit la même mise à jour"], tsize=14)
    s.boite(340, 100, 220, 340, "Ingress puis Service back", ["/api -> back:8000", "10.43.201.5, 3 pods", "le flux SSE repasse ici", "proxy-buffering off,", "délai de lecture 3600 s"], tsize=13)
    s.fleche([(340, 175), (300, 175)], "or")
    s.fleche([(340, 365), (300, 365)], "or")
    s.chip(320, 205, "SSE", OR_CLAIR)
    ys = [100, 252, 404]
    noms = [("back-7c5b9-h4n6r", "10.42.1.21"), ("back-7c5b9-j8v3d", "10.42.2.23"), ("back-7c5b9-q2l7s", "10.42.2.24")]
    for y, (n, ip) in zip(ys, noms):
        bid = s.nid()
        s.rect(600, y, 400, 136, CARTE, OR, 2, 10, None, None, bid)
        s.texte(614, y + 22, [(n, T1, True, 13), ("   " + ip, OR_CLAIR, False, 12)], c=bid)
        for i, l in enumerate(("réservation : SET verrou NX EX 600", "changement : PUBLISH seance:<id>", "UNE connexion SUBSCRIBE, relais en SSE")):
            s.texte(614, y + 48 + 20 * i, [(l, T2, False, 12)], c=bid)
        s.fleche([(600, y + 68), (560, y + 68)], "or")
    # Service redis et pod redis
    s.texte(1090, 90, [("commandes : SET NX EX, INCR, PUBLISH, SUBSCRIBE", T2, False, 12)])
    s.service(1090, 100, 470, "redis", "10.43.62.101", "6379")
    for y in ys:
        s.fleche([(1000, y + 50), (1040, y + 50), (1040, 123), (1090, 123)], "or", 2)
    s.fleche([(1325, 146), (1325, 200)], "bleu")
    rid = s.nid()
    s.rect(1090, 200, 470, 480, CARTE, GRIS, 1.5, 10, None, None, rid)
    s.texte(1106, 224, [("Pod redis", T1, True, 14), ("   10.42.2.9 :6379", OR_CLAIR, False, 12)], c=rid)
    cartes = [("1. Verrous de sièges", ["clé verrou:{séance}:{siège}", "SET NX avec expiration de 10 min", "libération par script Lua atomique"]),
              ("2. Compteurs de remplissage", ["clé remplissage:<séance>", "INCR et DECR à chaque réservation", "lus pour afficher le taux de remplissage"]),
              ("3. Pub/sub", ["canaux seance:<id> et remplissage", "PUBLISH à chaque changement", "chaque back reçoit via sa connexion SUBSCRIBE"])]
    for i, (t, ls) in enumerate(cartes):
        carte(s, 1106, 244 + i * 112, 438, 102, t, ls, stroke=OR if i == 2 else BORD)
    s.texte(1106, 598, [("--save \"\" --appendonly no : aucune persistance", T3, False, 12)], c=rid)
    s.texte(1106, 616, [("maxmemory 100mb, noeviction : refuse plutôt qu'évincer", T3, False, 12)], c=rid)
    s.texte(1106, 634, [("requests 100m / 100Mi, limits 200m / 200Mi", T3, False, 12)], c=rid)
    for y in ys:
        s.fleche([(1106, 540 if False else 520), (1022, 520), (1022, y + 96), (1000, y + 96)], "gris", dash="5 4") if False else None
    s.fleche([(1090, 530), (1022, 530), (1022, 500), (1000, 500)], "gris", dash="5 4")
    s.fleche([(1022, 530), (1022, 348), (1000, 348)], "gris", dash="5 4", tete=True)
    s.fleche([(1022, 348), (1022, 196), (1000, 196)], "gris", dash="5 4")
    # arbitre
    s.boite(600, 590, 400, 120, "PostgreSQL : l'arbitre", ["index unique partiel (séance, siège)", "refuse la double réservation, même", "si Redis perd ou se trompe de verrou"], tsize=14)
    s.fleche([(800, 540), (800, 590)], "gris")
    s.chip(800, 565, "SQL final", T2)
    s.boite(40, 480, 520, 230, "Qui fait quoi",
            ["Redis : rapide, éphémère, partagé entre les 3 pods back", "verrou : bloque un siège pendant le paiement (10 min)",
             "compteur : taux de remplissage sans compter en base", "pub/sub : prévient tous les back, qui relaient en SSE",
             "PostgreSQL : décide en dernier, la réservation y est durable"], tsize=14)
    # isolation
    s.texte(1090, 872, [("NetworkPolicy redis : seul component=back peut entrer", T1, True, 13)])
    for x, w, n in ((1090, 140, "front"), (1245, 150, "qr-generator"), (1410, 150, "qr-verifier")):
        bid = s.nid()
        s.rect(x, 790, w, 50, CARTE, ROUGE, 2, 8, None, None, bid)
        s.texte(x + w / 2, 820, [(n, T1, True, 12)], ancre="middle", c=bid)
        s.fleche([(x + w / 2, 790), (x + w / 2, 684)], "rouge", 2, dash="5 4")
        s.croix(x + w / 2, 737, ROUGE, 5)
    s.fleche([(1090, 880), (1130, 880)], "or") if False else None
    s.texte(1090, 892, [("le back (pods ci-contre) est le seul client autorisé", VERT, False, 12)])
    s.legende(40, 940, [("fleche", "or", "requête ou flux SSE"), ("pointille", "gris", "message publié, reçu par chaque back"), ("fleche", "rouge", "refusé par la NetworkPolicy"),
                        ("fleche", "bleu", "Service -> pod")], 1500)


# ================================================================ défi 15 : cycle de vie Helm et hooks
def voie(s, y, h, titre, sous):
    bid = s.nid()
    s.rect(60, y, 1500, h, "#100f0b", GRIS, 1.2, 12, None, None, bid)
    s.texte(76, y + 28, [(titre, T1, True, 14)], c=bid)
    for i, l in enumerate(sous):
        s.texte(76, y + 49 + 18 * i, [(l, T3, False, 12)], c=bid)


def job(s, x, y, w, h, nom, poids, lignes, stroke=OR):
    bid = s.nid()
    s.rect(x, y, w, h, CARTE, stroke, 3, 8, None, None, bid)
    s.texte(x + 12, y + 22, [(nom, T1, True, 13)], c=bid)
    s.texte(x + w - 12, y + 22, [(poids, OR_CLAIR, False, 12)], ancre="end", c=bid)
    for i, l in enumerate(lignes):
        s.texte(x + 12, y + 44 + 18 * i, [(l, T3, False, 12)], c=bid)


@defi(15, "Défi 15 : cycle de vie d'une release Helm et hooks",
      "défi 15 : helm upgrade en bandes, hooks pre-upgrade, post-upgrade et post-delete", h=1140)
def defi15(s):
    s.fleche([(36, 70), (36, 970)], "or", 3)
    s.texte(36, 992, [("temps", T2, True, 12)], ancre="middle")
    # voie 0
    voie(s, 70, 100, "Avant tout", ["pre-install, pre-upgrade", "poids -20"])
    carte(s, 280, 86, 330, 66, "ServiceAccount cinetint-hooks", ["identité des pods Job"], nouveau=True)
    carte(s, 630, 86, 330, 66, "Role cinetint-hooks", ["ConfigMaps : get, create, patch, delete"], nouveau=True)
    carte(s, 980, 86, 330, 66, "RoleBinding cinetint-hooks", ["relie le rôle au compte"], nouveau=True)
    s.texte(1330, 114, [("créés avant les Jobs", T3, False, 12)])
    s.texte(1330, 132, [("qui s'en servent", T3, False, 12)])
    # voie 1
    voie(s, 190, 230, "pre-upgrade", ["avant la mise à jour", "Helm attend la fin de", "chaque Job avant d'avancer"])
    job(s, 280, 206, 340, 84, "Job config-avant", "poids 0", ["pod kubectl, compte cinetint-hooks", "écrit le carnet de déploiement"])
    s.fleche([(620, 248), (660, 248)], "gris")
    carte(s, 660, 206, 380, 84, "ConfigMap cinetint-deploiement", ["etat=en-cours, revision, versions", "debut=date de début"])
    s.texte(1070, 244, [("le carnet dit où en est le déploiement", T2, False, 12)])
    s.fleche([(450, 290), (450, 322)], "or")
    s.texte(466, 311, [("puis, poids 5", T3, False, 12)])
    job(s, 280, 322, 340, 84, "Job sauvegarde-avant", "poids 5", ["pod postgres:17-alpine : pg_dump -Fc", "lit la base par le Service postgres"])
    s.fleche([(620, 364), (660, 364)], "gris")
    carte(s, 660, 322, 380, 84, "PVC cinetint-sauvegardes", ["200Mi, distinct de data-postgres-0", "reçoit le fichier .dump d'avant"])
    s.texte(1070, 360, [("rendu seulement si le volume existe déjà", T2, False, 12)])
    # voie 2
    voie(s, 440, 140, "Application", ["Helm applique", "les manifests"])
    for i, nom in enumerate(("front", "back", "qr-generator", "qr-verifier")):
        carte(s, 280 + i * 270, 458, 250, 100, "Deployment " + nom, ["mise à jour progressive,", "un pod à la fois", "maxSurge 1, maxUnavailable 0"], tsize=12)
    s.texte(1370, 500, [("postgres et redis :", T3, False, 12)])
    s.texte(1370, 518, [("inchangés ici", T3, False, 12)])
    # voie 3
    voie(s, 600, 230, "post-upgrade", ["après la mise à jour", "poids 0 puis poids 5"])
    job(s, 280, 616, 340, 84, "Job config-apres", "poids 0", ["test de fumée des 4 services", "puis écrit etat=termine"])
    s.fleche([(620, 658), (660, 658)], "gris")
    carte(s, 660, 616, 380, 84, "ConfigMap cinetint-deploiement", ["etat=termine, sante, fin", "le Job échoue si un service ne répond pas"])
    s.texte(1070, 654, [("la release n'est « terminée » qu'après le test", T2, False, 12)])
    s.fleche([(450, 700), (450, 732)], "or")
    s.texte(466, 721, [("puis, poids 5", T3, False, 12)])
    job(s, 280, 732, 340, 84, "Job sauvegarde-apres", "poids 5", ["pod postgres:17-alpine : pg_dump -Fc", "état final de la base"])
    s.fleche([(620, 774), (660, 774)], "gris")
    carte(s, 660, 732, 380, 84, "PVC cinetint-sauvegardes", ["même volume : un second .dump", "étiquette apres-rev<N>"])
    s.texte(1070, 770, [("avant et après : on peut revenir en arrière", T2, False, 12)])
    # voie 4
    voie(s, 850, 120, "post-delete", ["à helm uninstall"])
    job(s, 280, 866, 340, 84, "Job nettoyage", "poids 0", ["kubectl delete configmap", "cinetint-deploiement"])
    s.fleche([(620, 908), (660, 908)], "rouge")
    carte(s, 660, 866, 380, 84, "ConfigMap supprimée", ["créée par un Job : Helm ne la connaît pas"], stroke=ROUGE)
    carte(s, 1070, 866, 460, 84, "PVC cinetint-sauvegardes : conservé", ["helm.sh/resource-policy: keep"], stroke=VERT)
    s.boite(60, 1000, 1500, 74, "Règle des hooks",
            ["chaque hook est un Job (pod éphémère, hook-delete-policy hook-succeeded : supprimé après succès) ; Helm les lance par poids croissant, et si l'un échoue, la mise à jour s'arrête"], tsize=14)
    s.legende(60, 1104, [("fleche", "or", "ordre d'exécution"), ("fleche", "gris", "écrit dans"), ("nouveau", "or", "Job ou droit créé par ce défi"), ("boite", "rouge", "supprimé"), ("boite", "vert", "conservé")], 1500)


# ================================================================ défi 16 : sauvegardes et restauration
@defi(16, "Défi 16 : sauvegarde planifiée et restauration de la base",
      "défi 16 : CronJob, Job, pg_dump vers un volume dédié, puis restauration", h=1130)
def defi16(s):
    s.texte(40, 84, [("1. Sauvegarde planifiée, chaque nuit", OR, True, 15)])
    s.boite(40, 100, 340, 150, "CronJob cinetint-sauvegarde", ["schedule : 0 3 * * * (3 h chaque nuit)", "concurrencyPolicy : Forbid", "deux sauvegardes ne se chevauchent pas"], tsize=14, nouveau=True)
    s.fleche([(380, 175), (430, 175)], "or")
    s.texte(405, 162, [("crée", T2, False, 12)], ancre="middle")
    s.boite(430, 100, 320, 150, "Job de sauvegarde", ["un Job par exécution", "un pod, restartPolicy Never", "backoffLimit 2, délai 900 s"], tsize=14, nouveau=True)
    s.fleche([(750, 175), (800, 175)], "or")
    s.texte(775, 162, [("lance", T2, False, 12)], ancre="middle")
    s.boite(800, 100, 420, 150, "Pod postgres:17-alpine", [[("1  ", OR, True), ("pg_dump -Fc par le Service postgres", T2)],
                                                             [("2  ", OR, True), ("pg_restore --list : fichier lisible ?", T2)],
                                                             [("3  ", OR, True), ("rétention : garde les 7 derniers", T2)]], tsize=14, droite="component=sauvegarde", nouveau=True)
    s.fleche([(1220, 175), (1270, 175)], "or")
    s.boite(1270, 100, 290, 150, "PVC cinetint-sauvegardes", ["200Mi, ReadWriteOnce", "distinct de data-postgres-0", "survit à helm uninstall"], tsize=14, nouveau=True)
    s.service(800, 330, 420, "postgres", "10.43.230.74", "5432", ligne2="10.43.230.74 :5432  (lecture pour pg_dump)")
    s.fleche([(1010, 250), (1010, 330)], "or")
    s.texte(1026, 296, [("lecture en base", T2, False, 12)])
    s.boite(800, 410, 420, 100, "Pod postgres-0 (StatefulSet)", ["NetworkPolicy : component=sauvegarde", "est autorisé à joindre :5432"], tsize=14)
    s.fleche([(1010, 376), (1010, 410)], "bleu")
    s.coche(1190, 394, VERT, 5)
    carte(s, 1270, 410, 290, 100, "PVC data-postgres-0", ["100Mi, volume de la base", "séparé des sauvegardes"])
    s.boite(40, 330, 720, 180, "Pourquoi un volume séparé",
            ["si le volume de la base est perdu, les sauvegardes survivent", "pg_restore --list vérifie le fichier avant de le garder",
             "rétention 7 : les plus anciens fichiers sont supprimés", "la sauvegarde manuelle du défi 15 écrit dans le même volume"], tsize=14)
    # restauration
    s.texte(40, 596, [("2. Restauration, à la main, après avoir arrêté le back", OR, True, 15)])
    etapes = [("1", "back à 0 réplique", ["kubectl scale deployment back", "--replicas=0", "plus aucune écriture"]),
              ("2", "Job de restauration", ["component=sauvegarde : autorisé", "monte cinetint-sauvegardes", "FICHIER vide : le plus récent"]),
              ("3", "pg_restore", ["--clean --if-exists", "une seule transaction : si elle", "échoue, la base reste intacte"]),
              ("4", "back remis à 3", ["kubectl scale deployment back", "--replicas=3", "le service reprend"])]
    for i, (n, t, ls) in enumerate(etapes):
        x = 40 + i * 390
        bid = s.nid()
        s.rect(x, 616, 340, 130, CARTE, OR, 2, 10, None, None, bid)
        s.cercle(x + 24, 642, n, OR, FOND, r=12)
        s.texte(x + 46, 647, [(t, T1, True, 14)], c=bid)
        for k, l in enumerate(ls):
            s.texte(x + 16, 678 + 19 * k, [(l, T3, False, 12)], c=bid)
        if i < 3:
            s.fleche([(x + 340, 681), (x + 390, 681)], "or")
    # chemin des données
    s.texte(40, 790, [("Chemin des données pendant la restauration", T1, True, 14)])
    chain = [("PVC cinetint-sauvegardes", ["fichier .dump le plus récent"], OR), ("Pod du Job de restauration", ["postgres:17-alpine, pg_restore"], OR),
             ("Service postgres", ["10.43.230.74 :5432"], BLEU), ("Pod postgres-0", ["données remplacées, PVC conservé"], GRIS)]
    for i, (t, ls, coul) in enumerate(chain):
        x = 40 + i * 390
        s.boite(x, 806, 340, 90, t, ls, stroke=coul, tsize=13)
        if i < 3:
            s.fleche([(x + 340, 851), (x + 390, 851)], "or")
    s.boite(1090 + 0, 930, 470, 0, None) if False else None
    cid = s.nid()
    s.rect(40, 930, 760, 56, CARTE, GRIS, 1.2, 10, "5 4", 0.6, cid)
    s.texte(54, 954, [("back : 0 pod pendant la restauration", T1, True, 13)], c=cid)
    s.texte(54, 974, [("les Services front, qr-* et l'Ingress restent en place", T3, False, 12)], c=cid)
    s.boite(830, 930, 730, 56, None, [("FICHIER vide : la sauvegarde la plus récente ; sinon le nom du fichier .dump", T2)], tsize=13)
    s.legende(40, 1030, [("fleche", "or", "flux de la sauvegarde ou de la restauration"), ("fleche", "bleu", "Service -> pod"), ("fantome", "gris", "pod arrêté"),
                         ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)


# ================================================================ défi 18 : durcissement en quatre couches
def couche(s, y, h, num, titre, sous):
    bid = s.nid()
    s.rect(40, y, 1520, h, "#100f0b", OR, 1.5, 12, None, None, bid)
    s.cercle(70, y + 30, num, OR, FOND, r=16)
    s.texte(100, y + 36, [(titre, T1, True, 15), ("     " + sous, T3, False, 12)], c=bid)


MATRICE_SRC = ["ingress-nginx", "front", "back", "qr-generator", "qr-verifier", "redis", "postgres"]
MATRICE_DST = ["front", "back", "qr-generator", "qr-verifier", "redis", "postgres"]
AUTORISES = {("ingress-nginx", "front"), ("ingress-nginx", "back"), ("ingress-nginx", "qr-generator"), ("ingress-nginx", "qr-verifier"),
             ("front", "back"), ("qr-verifier", "back"), ("qr-verifier", "qr-generator"),
             ("back", "redis"), ("back", "postgres"), ("back", "qr-generator")}


@defi(18, "Défi 18 : durcissement de l'infrastructure en quatre couches",
      "défi 18 : Ingress limité, NetworkPolicy partout, pods durcis, Secrets générés", h=1240)
def defi18(s):
    # couche 1
    couche(s, 70, 196, "1", "Ingress : limiter ce qui entre", "le contrôleur ingress-nginx applique ces annotations à chaque requête")
    cartes = [("limit-rps : 20", ["20 requêtes par seconde", "et par adresse IP cliente"]), ("limit-connections : 30", ["30 connexions simultanées", "au plus par adresse IP"]),
              ("proxy-body-size : 1m", ["corps de requête limité à", "1 Mio : pas de gros envoi"]), ("délais de connexion", ["proxy-connect/read/send :", "un client lent ne bloque rien"])]
    for i, (t, ls) in enumerate(cartes):
        carte(s, 60 + i * 370, 126, 350, 80, t, ls, stroke=OR)
    s.texte(60, 240, [("Le flux SSE du back garde un délai de lecture long (3600 s) sur son propre Ingress.", T3, False, 12)])
    # couche 2 : matrice
    couche(s, 286, 382, "2", "NetworkPolicy : tout fermé, sauf ce qui sert", "une règle par composant, et isolation entre espaces de noms")
    x0, y0, cw, rh = 230, 372, 150, 32
    s.texte(x0 - 6, y0 - 8, [("de  \\  vers", T3, False, 12)], ancre="end")
    for j, d in enumerate(MATRICE_DST):
        s.texte(x0 + j * cw + cw / 2, y0 - 8, [(d, T1, True, 12)], ancre="middle")
    for i, src in enumerate(MATRICE_SRC):
        yy = y0 + i * rh
        s.texte(x0 - 6, yy + 21, [(src, T1, True, 12)], ancre="end")
        for j, d in enumerate(MATRICE_DST):
            ok = (src, d) in AUTORISES
            same = src == d
            s.rect(x0 + j * cw + 4, yy + 2, cw - 8, rh - 4, "#14201a" if ok else ("#0f0e0b" if same else "#1b1311"), VERT if ok else BORD, 1.5 if ok else 1, 5)
            if ok:
                s.coche(x0 + j * cw + cw / 2, yy + rh / 2 + 1, VERT, 4)
            elif not same:
                s.texte(x0 + j * cw + cw / 2, yy + 21, [("refusé", "#9a5a52", False, 12)], ancre="middle")
    s.boite(1160, 354, 380, 232, "Lecture de la matrice", ["case verte : flux autorisé", "(ingress.from et ports)", "toute autre case : refusé", "front vers la base : refusé,", "il passe par le back", "un pod d'un autre espace de", "noms ne joint rien"], tsize=14, nouveau=True)
    s.texte(60, 638, [("Étiquettes app.kubernetes.io/component : front, back, qr-generator, qr-verifier, redis, postgres, sauvegarde, test.", T3, False, 12)])
    s.texte(60, 656, [("Un pod sans l'étiquette attendue, du même espace de noms ou d'un autre : le paquet est jeté sur le veth du pod de destination.", T3, False, 12)])
    # couche 3
    couche(s, 688, 272, "3", "Pod : un conteneur sans privilèges", "securityContext de chaque pod applicatif et de la base, posé par la charte")
    reglages = [("runAsNonRoot, uid 1000", ["70 pour postgres, 999 pour redis", "aucun processus root"]),
                ("allowPrivilegeEscalation : false", ["un processus ne peut pas", "gagner des droits"]),
                ("capabilities : drop ALL", ["aucune capacité Linux", "(pas de NET_RAW, pas de chown)"]),
                ("readOnlyRootFilesystem : true", ["système de fichiers en lecture", "seule, emptyDir sur /tmp"]),
                ("seccomp : RuntimeDefault", ["appels système filtrés par", "le profil par défaut du runtime"]),
                ("automountServiceAccountToken : false", ["le pod ne reçoit aucun jeton", "pour parler à l'API server"])]
    for i, (t, ls) in enumerate(reglages):
        carte(s, 60 + (i % 3) * 495, 740 + (i // 3) * 108, 475, 96, t, ls, stroke=OR)
    # couche 4
    couche(s, 980, 140, "4", "Secrets : générés, jamais écrits", "mots de passe et clé de signature créés par la charte")
    secrets = [("mots de passe aléatoires", ["POSTGRES_PASSWORD et autres,", "générés au premier install"]), ("clé de signature Ed25519", ["Secret cinetint-cle, montée", "dans qr-generator et qr-verifier"]),
               ("jamais dans le dépôt", ["ni dans values.yaml : conservés", "tels quels aux mises à jour"])]
    for i, (t, ls) in enumerate(secrets):
        carte(s, 60 + i * 495, 1032, 475, 76, t, ls, stroke=OR)
    s.legende(40, 1156, [("boite", "vert", "flux autorisé"), ("nouveau", "or", "NOUVEAU : protection ajoutée par ce défi")], 1500)
    s.texte(40, 1200, [("Les quatre couches s'ajoutent : une requête franchit l'Ingress, puis la NetworkPolicy, puis atteint un pod qui ne peut presque rien faire.", T3, False, 12)])


# ================================================================ défi 19 : pipeline GitHub Actions
def porte(s, cx, cy, n):
    s.o.append('<path d="M%g,%g L%g,%g L%g,%g L%g,%g z" fill="%s" stroke="%s" stroke-width="2"/>' % (cx, cy - 17, cx + 17, cy, cx, cy + 17, cx - 17, cy, OR, FOND))
    s.o.append('<text x="%g" y="%g" text-anchor="middle" fill="%s" font-size="13" font-weight="700"%s>%s</text>' % (cx, cy + 4.5, FOND, s.dc(), n))


def job_ci(s, x, y, w, h, titre, lignes, droite=None, stroke=GRIS, nouveau=False):
    return s.boite(x, y, w, h, titre, lignes, stroke=stroke, tsize=14, droite=droite, nouveau=nouveau)


@defi(19, "Défi 19 : intégration continue avec GitHub Actions",
      "défi 19 : tests, images, cluster kind éphémère, publication et déploiement manuel", h=870)
def defi19(s):
    H = 250
    s.boite(40, 100, 190, H, "Déclencheurs", ["push", "pull_request", "workflow_dispatch", "", "fichier :", ".github/workflows/", "ci.yml"], tsize=14)
    job_ci(s, 270, 100, 300, H, "Job tests", ["back : pytest", "qr-generator : pytest", "qr-verifier : pytest", "front : tests", "", "services du job :", "PostgreSQL 17 et Redis 8"], droite="ubuntu")
    job_ci(s, 610, 100, 270, H, "Job images", ["build des 4 images :", "front, back,", "qr-generator, qr-verifier", "cache de couches", "(GitHub Actions)", "tag : SHA du commit", "needs : tests"])
    job_ci(s, 920, 100, 370, H, "Job kind", ["cluster éphémère :", "1 control-plane + 2 workers", "Calico, ingress-nginx, metrics-server", "chargement des images", "helm lint, helm install, helm test", "test de fumée : parcours complet", "par l'Ingress", "essai de mise à jour progressive"],
           droite="needs : images", stroke=OR)
    job_ci(s, 1330, 100, 230, H, "Job publication", ["docker push", "vers ghcr.io", "les 4 images", "", "if : branche main", "needs : kind", "tout doit être vert"], stroke=OR)
    for (xa, xb, n) in ((230, 270, None), (570, 610, 1), (880, 920, 2), (1290, 1330, 3)):
        s.fleche([(xa, 250), (xb, 250)], "or", 3)
        if n:
            porte(s, (xa + xb) / 2, 218, n)
    # déploiement
    s.fleche([(1445, 350), (1445, 420)], "or", 3)
    porte(s, 1445, 385, 4)
    s.boite(920, 420, 640, 130, "Déploiement manuel (optionnel)", ["workflow_dispatch : lancé par une personne", "secret KUBECONFIG du dépôt GitHub", "helm upgrade --install sur le cluster du cours"], tsize=14, nouveau=True)
    s.fleche([(1240, 550), (1240, 590)], "or", 3)
    s.boite(920, 590, 640, 100, "Cluster du cours (RKE2, espace de noms u-XXX)", ["images tirées de ghcr.io", "la charte cinetint est installée comme au défi 6"], tsize=14)
    # portes
    s.boite(40, 400, 840, 180, "Portes de qualité (losanges or)",
            [[("1  ", OR, True), ("tests : les 4 services passent leurs tests avec une vraie base et un vrai Redis", T2)],
             [("2  ", OR, True), ("images : les 4 images se construisent, aucun Dockerfile cassé", T2)],
             [("3  ", OR, True), ("kind : la charte s'installe, tous les pods sont Ready, helm test passe,", T2)],
             [("    ", OR, True), ("le parcours complet par l'Ingress marche, la mise à jour ne coupe rien", T2)],
             [("4  ", OR, True), ("publication : seulement sur main, et seulement si 1, 2 et 3 sont verts", T2)]], tsize=14, nouveau=True)
    s.boite(40, 600, 840, 90, "Pourquoi un cluster kind dans la CI",
            ["la charte Helm est essayée sur un vrai Kubernetes (Calico, Ingress, metrics-server)", "avant d'arriver sur le cluster du cours"], tsize=14)
    s.legende(40, 740, [("fleche", "or", "enchaînement (needs)"), ("boite", "or", "job qui garde une porte"), ("nouveau", "or", "NOUVEAU dans ce défi")], 1500)
    s.texte(40, 790, [("Si une porte échoue, tout ce qui suit est arrêté : rien n'est publié et rien n'est déployé tant que les tests, les images et le cluster kind ne sont pas verts.", T3, False, 12)])


# ================================================================ défi 20 : migration de base sans interruption
def pod_mig(s, x, y, w, nom, ver, texte, etat, change=False, h=50):
    """etat : ready, migre, gone (pod prévu mais non exécuté)."""
    bid = s.nid()
    stroke, dash, op, tcol = {"ready": (VERT, None, None, VERT), "migre": (OR_CLAIR, "5 4", None, OR_CLAIR),
                              "gone": (GRIS, "3 3", 0.5, GRIS)}[etat]
    sw = 1.5
    if change:
        stroke, sw = OR, 3
    s.rect(x, y, w, h, CARTE, stroke, sw, 8, dash, op, bid)
    s.texte(x + 10, y + 19, [(nom, T1, True, 12), ("  " + ver, OR_CLAIR if ver == "v2" else BLEU_CLAIR, True, 12)], c=bid)
    s.texte(x + 10, y + 38, [(texte, tcol, False, 12)], c=bid)


@defi(20, "Défi 20 : migration de base de données sans interruption (expand puis contract)",
      "défi 20 : migration Alembic pendant une mise à jour progressive, sans interruption", h=1170)
def defi20(s):
    # ce qui ne bouge pas
    s.boite(30, 58, 190, 72, "Ingress", ["/api  ->  back"], tsize=14)
    s.fleche([(220, 94), (250, 94)], "or")
    s.service(250, 58, 330, "back", "10.43.201.5", "8000", h=72, ligne2="10.43.201.5 :8000  (inchangé)")
    s.fleche([(580, 94), (610, 94)], "or")
    s.boite(610, 58, 470, 72, "Deployment back : RollingUpdate", ["maxSurge 1, maxUnavailable 0, readinessProbe /api/sante"], tsize=13)
    s.boite(1110, 58, 460, 72, "PostgreSQL primaire + réplique en flux", ["tables commandes et alembic_version"], tsize=13)
    s.fleche([(30, 148), (1570, 148)], "or", 2)
    s.chip(800, 148, "temps : le schéma change pendant que le service répond", T2)

    cols = [
        dict(t="P0", titre="avant", d="3 pods v2, alembic_version = 0001", fut=False,
             pods=[("back-5c8d4-h4n6r", "v2", "Ready : sert, schéma 0001", "ready"), ("back-5c8d4-j8v3d", "v2", "Ready : sert, schéma 0001", "ready"),
                   ("back-5c8d4-q2l7s", "v2", "Ready : sert, schéma 0001", "ready"), None],
             ep="3 endpoints v2",
             db=["table commandes : sans canal_detail", "alembic_version = 0001", "1325 commandes, 11759 billets"],
             compat=["v2 : INSERT et SELECT sans canal_detail"]),
        dict(t="P1", titre="expand : un pod v3 démarre", d="helm upgrade --set images.tags.back=v3", fut=False,
             pods=[("back-5c8d4-h4n6r", "v2", "Ready : sert encore", "ready"), ("back-5c8d4-j8v3d", "v2", "Ready : sert encore", "ready"),
                   ("back-5c8d4-q2l7s", "v2", "Ready : sert encore", "ready"), ("back-9a1f3-k7m2x", "v3", "migre : alembic upgrade head", "migre")],
             ep="3 endpoints v2, v3 en attente",
             db=["alembic upgrade head (pod v3)", "sous pg_advisory_lock(856690)", "ADD COLUMN canal_detail varchar(24)", "NOT NULL DEFAULT 'standard'", "lock_timeout 5 s, sans réécriture"],
             compat=["v2 : INSERT sans la colonne (la base met", "'standard'), SELECT sans la demander", "autres v3 : même verrou, base déjà à", "jour, ils ne font rien"]),
        dict(t="P2", titre="fin", d="3 pods v3, alembic_version = 0002", fut=False,
             pods=[("back-9a1f3-k7m2x", "v3", "Ready : lit et écrit canal_detail", "ready"), ("back-9a1f3-p3w9c", "v3", "Ready : lit et écrit canal_detail", "ready"),
                   ("back-9a1f3-t6n4v", "v3", "Ready : lit et écrit canal_detail", "ready"), None],
             ep="3 endpoints v3",
             db=["alembic_version = 0002", "canal_detail ajoutée à commandes", "1325 commandes, toutes à 'standard'", "11759 billets avant et après", "0 donnée perdue"],
             compat=["v3 lit et écrit canal_detail", "plus aucun pod v2 en service"]),
        dict(t="P3", titre="contract (plus tard)", d="version suivante, non exécutée", fut=True,
             pods=[("back-… ", "v4", "non exécuté", "gone"), ("back-… ", "v4", "non exécuté", "gone"), ("back-… ", "v4", "non exécuté", "gone"), None],
             ep="à venir",
             db=["migration ultérieure :", "suppression d'une ancienne colonne,", "contrainte resserrée", "seulement quand aucun pod", "n'utilise plus l'ancien schéma"],
             compat=["aucun pod sur l'ancien schéma :", "on peut resserrer sans casser personne"]),
    ]
    cw, gap = 370, 20
    prev = None
    for i, c in enumerate(cols):
        x = 30 + i * (cw + gap)
        hid = s.nid()
        s.rect(x, 158, cw, 54, CARTE2, GRIS if c["fut"] else OR, 1.5, 10, "5 4" if c["fut"] else None, 0.7 if c["fut"] else None, hid)
        s.texte(x + 14, 180, [(c["t"], OR, True, 17), ("  " + c["titre"], T1, True, 14)], c=hid)
        s.texte(x + 14, 201, [(c["d"], T3, False, 12)], c=hid)
        pid = s.nid()
        s.rect(x, 222, cw, 272, "#100f0b", GRIS, 1.2, 10, "5 4" if c["fut"] else None, None, pid)
        s.texte(x + 14, 244, [("Pods back", T1, True, 13)], c=pid)
        s.texte(x + cw - 12, 244, [(c["ep"], BLEU_CLAIR, False, 12)], ancre="end", c=pid)
        for j, p in enumerate(c["pods"]):
            if p is None:
                continue
            chg = prev is not None and (prev["pods"][j] is None or prev["pods"][j][1:4:2] != p[1:4:2])
            if prev is None:
                chg = False
            pod_mig(s, x + 14, 258 + j * 58, cw - 28, p[0], p[1], p[2], p[3], chg and not c["fut"])
        s.boite(x, 504, cw, 164, "PostgreSQL", c["db"], tsize=13, stroke=OR if i == 1 else BORD, nouveau=(i == 1),
                dash="5 4" if c["fut"] else None, op=0.8 if c["fut"] else None)
        s.boite(x, 678, cw, 130, "Ce que font les pods", c["compat"], tsize=13, dash="5 4" if c["fut"] else None, op=0.8 if c["fut"] else None)
        prev = c

    # règle d'or et mesure
    s.boite(30, 828, 760, 112, "Règle d'or", [[("chaque migration doit être compatible avec la version ", T2), ("PRÉCÉDENTE", OR_CLAIR, True), (" du code", T2)],
                                              "ajouter avant de retirer : jamais renommer ni supprimer", "en une seule étape"], tsize=14, nouveau=True)
    s.boite(820, 828, 750, 112, "Mesure pendant les trois mises à jour", ["charge d'écriture continue : créer puis annuler une commande, 6 fois par seconde",
                                                                      [("écritures : ", T2), ("560 tours réussis, 0 erreur", VERT, True)],
                                                                      [("lectures : ", T2), ("1182 requêtes, toutes en HTTP 200", VERT, True)]], tsize=14, stroke=VERT)
    s.boite(30, 958, 1540, 130, "Limite constatée : le retour arrière du code", [
        [("vers une image SANS la migration 0002, le retour échoue : alembic « Can't locate revision identified by '0002' »", T2)],
        [("le nouveau ReplicaSet reste bloqué ; les anciens pods servent toujours, donc aucune erreur, mais le rollout dépasse son délai", T2)],
        [("solution : chaque image contient toutes les migrations déjà appliquées ; on ne revient jamais en arrière sur le schéma, seulement sur le code", VERT)]],
        tsize=14, stroke=ROUGE, tfill="#e08a7f", fill="#1b1311")
    s.legende(30, 1118, [("boite", "vert", "pod Ready"), ("fantome", "gris", "pod en cours de migration ou prévu plus tard"),
                         ("nouveau", "or", "ce qui change à cet instant")], 1500)


# ================================================================ programme principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seulement", type=int, action="append", help="ne générer que ce défi (répétable)")
    ap.add_argument("--sortie", help="répertoire de sortie (défaut : le dossier k8s du dépôt)")
    ap.add_argument("--debug", action="store_true", help="ajoute des attributs de contrôle utilisés par le test de rendu")
    a = ap.parse_args()
    racine = a.sortie or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    avert = []
    for num in sorted(DEFIS):
        if a.seulement and num not in a.seulement:
            continue
        w, h, titre_doc, sous, fn = DEFIS[num]
        s = Schema(num, w, h, sous, titre_doc, a.debug)
        fn(s)
        s.entete()
        d = os.path.join(racine, "defi%d" % num)
        os.makedirs(d, exist_ok=True)
        contenu = s.svg()
        if chr(0x2014) in contenu or chr(0x2013) in contenu:   # tirets cadratins interdits
            print("ERREUR : tiret cadratin ou demi-cadratin dans le défi %d" % num, file=sys.stderr)
            return 1
        with open(os.path.join(d, "schema.svg"), "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        avert += s.avert
        print("defi%d/schema.svg écrit (%d octets)" % (num, len(contenu.encode("utf-8"))))
    for m in avert:
        print("ATTENTION", m, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
