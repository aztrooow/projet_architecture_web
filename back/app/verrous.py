"""Verrous temporaires sur les sièges pendant le paiement.

Une clé Redis par siège, avec une durée de vie : si le spectateur abandonne,
la clé expire seule et le siège redevient vendable. Les clés d'une même séance
partagent le hash tag {seance} pour rester sur le même noeud en cluster.
"""

from .temps_reel import redis

# pose tous les verrous ou aucun ; renvoie les positions (1..n) des sièges déjà pris
_POSER = redis.register_script(
    """
    local conflits = {}
    for i, cle in ipairs(KEYS) do
        local proprietaire = redis.call('GET', cle)
        if proprietaire and proprietaire ~= ARGV[1] then
            table.insert(conflits, i)
        end
    end
    if #conflits > 0 then
        return conflits
    end
    for _, cle in ipairs(KEYS) do
        redis.call('SET', cle, ARGV[1], 'EX', tonumber(ARGV[2]))
    end
    return {}
    """
)

# ne supprime que les verrous qui appartiennent bien à la commande
_LIBERER = redis.register_script(
    """
    local n = 0
    for _, cle in ipairs(KEYS) do
        if redis.call('GET', cle) == ARGV[1] then
            redis.call('DEL', cle)
            n = n + 1
        end
    end
    return n
    """
)


def cle(seance_id: int, siege_id: int) -> str:
    return f"verrou:{{{seance_id}}}:{siege_id}"


async def poser(seance_id: int, siege_ids: list[int], proprietaire: str, duree_s: int) -> list[int]:
    """Renvoie la liste des sièges en conflit (vide si les verrous sont posés)."""
    cles = [cle(seance_id, s) for s in siege_ids]
    positions = await _POSER(keys=cles, args=[proprietaire, duree_s])
    return [siege_ids[p - 1] for p in positions]


async def liberer(seance_id: int, siege_ids: list[int], proprietaire: str) -> int:
    if not siege_ids:
        return 0
    return await _LIBERER(keys=[cle(seance_id, s) for s in siege_ids], args=[proprietaire])


async def proprietaires(seance_id: int, siege_ids: list[int]) -> dict[int, str]:
    """Siège -> commande qui le bloque, pour les sièges verrouillés seulement."""
    if not siege_ids:
        return {}
    valeurs = await redis.mget([cle(seance_id, s) for s in siege_ids])
    return {s: v for s, v in zip(siege_ids, valeurs) if v}
