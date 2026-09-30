import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api, ErreurApi, urlApi } from '../api.ts'
import { estBorne } from '../borne.ts'
import Affiche from '../components/Affiche.tsx'
import PlanSalle from '../components/PlanSalle.tsx'
import { dateLongue, duree, euros, heure, place, typeProduction } from '../format.ts'
import type { Commande, EtatSiege, Plan, Seance, Siege } from '../types.ts'

export default function SeancePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const borne = estBorne()
  const [seance, setSeance] = useState<Seance | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [choix, setChoix] = useState<Map<number, string>>(new Map())
  const [erreur, setErreur] = useState<string | null>(null)
  const [alerte, setAlerte] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)
  const choixCourant = useRef(choix)
  choixCourant.current = choix

  const rechargerPlan = useCallback(async () => {
    const nouveau = await api<Plan>(`/api/seances/${id}/plan`)
    setPlan(nouveau)
    // une place prise entre-temps quitte la sélection
    setChoix((actuel) => {
      const libres = new Set(nouveau.sieges.filter((s) => s.etat === 'libre').map((s) => s.id))
      const garde = new Map([...actuel].filter(([siege]) => libres.has(siege)))
      return garde.size === actuel.size ? actuel : garde
    })
  }, [id])

  useEffect(() => {
    setErreur(null)
    Promise.all([api<Seance>(`/api/seances/${id}`), api<Plan>(`/api/seances/${id}/plan`)])
      .then(([s, p]) => {
        setSeance(s)
        setPlan(p)
      })
      .catch((e: ErreurApi) => setErreur(e.statut === 404 ? 'Cette séance n’existe plus.' : e.message))
  }, [id])

  // temps réel : chaque siège réservé ou vendu ailleurs est grisé tout de suite
  useEffect(() => {
    const flux = new EventSource(urlApi(`/api/seances/${id}/flux`))
    flux.onmessage = (message) => {
      const { sieges } = JSON.parse(message.data) as { sieges: { id: number; etat: EtatSiege }[] }
      const etats = new Map(sieges.map((s) => [s.id, s.etat]))
      setPlan((p) => p && { ...p, sieges: p.sieges.map((s) => (etats.has(s.id) ? { ...s, etat: etats.get(s.id)! } : s)) })
      const perdus = [...choixCourant.current.keys()].filter((s) => etats.has(s) && etats.get(s) !== 'libre')
      if (perdus.length) {
        setChoix((actuel) => new Map([...actuel].filter(([siege]) => !perdus.includes(siege))))
        setAlerte('Une place que vous aviez choisie vient d’être réservée par quelqu’un d’autre.')
      }
    }
    // les verrous expirés ne sont pas annoncés : on relit le plan de temps en temps
    const minuteur = window.setInterval(() => rechargerPlan().catch(() => undefined), 30_000)
    return () => {
      flux.close()
      window.clearInterval(minuteur)
    }
  }, [id, rechargerPlan])

  const tarifs = useMemo(() => new Map(seance?.tarifs.map((t) => [t.categorie, t]) ?? []), [seance])
  const parDefaut = seance?.tarifs[0]?.categorie ?? 'plein'
  const sieges = useMemo(() => new Map(plan?.sieges.map((s) => [s.id, s]) ?? []), [plan])
  const selection = [...choix].map(([siege, categorie]) => ({ siege: sieges.get(siege)!, tarif: tarifs.get(categorie)! }))
  const total = selection.reduce((somme, l) => somme + (l.tarif?.prix_centimes ?? 0), 0)

  function basculer(siege: Siege) {
    setAlerte(null)
    const suivant = new Map(choix)
    if (suivant.has(siege.id)) suivant.delete(siege.id)
    else if (seance && suivant.size >= seance.places_max) {
      setAlerte(`${seance.places_max} places au maximum par commande.`)
      return
    } else suivant.set(siege.id, parDefaut)
    setChoix(suivant)
  }

  async function reserver() {
    if (!seance || !choix.size) return
    setEnvoi(true)
    setAlerte(null)
    try {
      const commande = await api<Commande>('/api/commandes', {
        method: 'POST',
        body: JSON.stringify({
          seance_id: seance.id,
          canal: borne ? 'borne' : 'web',
          places: [...choix].map(([siege_id, categorie]) => ({ siege_id, categorie })),
        }),
      })
      navigate(`/paiement/${commande.id}`)
    } catch (e) {
      const err = e as ErreurApi
      setAlerte(err.message)
      if (err.statut === 409) await rechargerPlan()
    } finally {
      setEnvoi(false)
    }
  }

  if (erreur)
    return (
      <section className="page page--etroite etat-vide">
        <h1>Séance indisponible</h1>
        <p>{erreur}</p>
        <a className="bouton" href={borne ? '/borne' : '/'}>
          Voir la programmation
        </a>
      </section>
    )

  if (!seance || !plan) return <SqueletteSeance />

  const film = seance.film
  const restantes = seance.salle.capacite - seance.vendus
  const evenement = seance.evenement

  return (
    <div className={`reservation${borne ? ' reservation--borne' : ''}${choix.size ? ' reservation--selection' : ''}`}>
      <header className="reservation__entete" style={{ '--teinte': film.couleur } as CSSProperties}>
        <Affiche film={film} taille="petite" />
        <div>
          <p className="reservation__fil">
            <a href={borne ? '/borne' : `/films/${film.id}`}>{borne ? 'Programmation' : 'Toutes les séances du film'}</a>
          </p>
          <h1>{film.titre}</h1>
          <p className="reservation__infos">
            <span className="capitalise">{dateLongue(seance.debut)}</span> à <strong>{heure(seance.debut)}</strong>
            <span>{seance.salle.nom}</span>
            <span>{seance.version}</span>
            {typeProduction(film.type_production) && <span>{typeProduction(film.type_production)}</span>}
            <span>{duree(film.duree_min)}</span>
          </p>
        </div>
      </header>

      {evenement && (
        <aside className="bandeau-evenement">
          <strong>{evenement.nom}</strong>
          <span>
            Séance évènement, tarif unique de {euros(seance.tarifs[0]?.prix_centimes ?? 0)} pour toutes les places.
          </span>
        </aside>
      )}

      {seance.commencee ? (
        <section className="etat-vide">
          <h2>La séance a commencé</h2>
          <p>La vente en ligne est fermée pour cette séance.</p>
        </section>
      ) : (
        <div className="reservation__corps">
          <section className="reservation__salle" aria-labelledby="titre-plan">
            <div className="reservation__titre-plan">
              <h2 id="titre-plan">Choisissez vos places</h2>
              <p>{restantes > 0 ? `${restantes} places libres sur ${seance.salle.capacite}` : 'Séance complète'}</p>
            </div>
            <PlanSalle plan={plan} choix={choix} onBasculer={basculer} />
          </section>

          <aside className="panier" aria-live="polite">
            <h2>Votre sélection</h2>
            {selection.length === 0 ? (
              <p className="panier__vide">
                Touchez un siège libre sur le plan. Jusqu’à {seance.places_max} places par commande.
              </p>
            ) : (
              <ul className="panier__lignes">
                {selection.map(({ siege, tarif }) => (
                  <li key={siege.id}>
                    <span className="panier__place">{place(siege)}</span>
                    <label className="visuellement-cache" htmlFor={`tarif-${siege.id}`}>
                      Tarif pour la place {place(siege)}
                    </label>
                    <select
                      id={`tarif-${siege.id}`}
                      value={tarif?.categorie}
                      onChange={(e) => setChoix((c) => new Map(c).set(siege.id, e.target.value))}
                    >
                      {seance.tarifs.map((t) => (
                        <option key={t.categorie} value={t.categorie}>
                          {t.categorie_libelle}
                        </option>
                      ))}
                    </select>
                    <span className="panier__prix">{tarif && euros(tarif.prix_centimes)}</span>
                    <span className="panier__libelle">{tarif?.libelle}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="panier__total">
              <span>Total</span>
              <strong>{euros(total)}</strong>
            </div>
            {alerte && (
              <p className="message message--alerte" role="alert">
                {alerte}
              </p>
            )}
            <button type="button" className="bouton bouton--plein" disabled={!choix.size || envoi} onClick={reserver}>
              {envoi ? 'Réservation…' : 'Continuer vers le paiement'}
            </button>
            <p className="panier__note">
              Vos places sont bloquées {seance.duree_verrou_min} minutes pendant le paiement.
            </p>
            <details className="panier__grille">
              <summary>Tarifs de cette séance</summary>
              <ul>
                {seance.tarifs.map((t) => (
                  <li key={t.categorie}>
                    <span>{t.categorie_libelle}</span>
                    <span>{euros(t.prix_centimes)}</span>
                  </li>
                ))}
              </ul>
            </details>
            {!borne && (
              <p className="panier__retour">
                <Link to="/" reloadDocument>
                  Changer de séance
                </Link>
              </p>
            )}
          </aside>
        </div>
      )}

      {choix.size > 0 && (
        <div className="barre-mobile">
          <p className="barre-mobile__total">
            <span>
              {choix.size} place{choix.size > 1 ? 's' : ''}
            </span>
            <strong>{euros(total)}</strong>
          </p>
          <button type="button" className="bouton bouton--plein" disabled={envoi} onClick={reserver}>
            {envoi ? 'Réservation…' : 'Continuer'}
          </button>
        </div>
      )}
    </div>
  )
}

function SqueletteSeance() {
  return (
    <div className="reservation" aria-busy="true">
      <div className="squelette squelette--entete" />
      <div className="reservation__corps">
        <div className="squelette squelette--plan" />
        <div className="squelette squelette--panier" />
      </div>
    </div>
  )
}
