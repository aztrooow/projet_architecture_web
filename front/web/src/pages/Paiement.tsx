import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { api, ErreurApi } from '../api.ts'
import { estBorne } from '../borne.ts'
import { dateLongue, euros, heure, place } from '../format.ts'
import type { Commande } from '../types.ts'

// Page du prestataire de paiement. Le vrai prestataire du cinéma n'étant pas
// branché, on simule sa réponse : aucune donnée de carte n'est saisie ici.
export default function Paiement() {
  const { id } = useParams()
  const navigate = useNavigate()
  const borne = estBorne()
  const [commande, setCommande] = useState<Commande | null>(null)
  const [restant, setRestant] = useState<number>(0)
  const [etat, setEtat] = useState<'attente' | 'traitement' | 'refuse'>('attente')
  const [erreur, setErreur] = useState<string | null>(null)

  const charger = useCallback(async () => {
    try {
      const c = await api<Commande>(`/api/commandes/${id}`)
      if (c.statut === 'payee') navigate(`/commande/${c.id}`, { replace: true })
      setCommande(c)
    } catch (e) {
      setErreur((e as ErreurApi).message)
    }
  }, [id, navigate])

  useEffect(() => {
    charger()
  }, [charger])

  useEffect(() => {
    if (!commande || commande.statut !== 'en_attente') return
    const fin = new Date(commande.expire_le).getTime()
    const tic = () => {
      const secondes = Math.max(0, Math.round((fin - Date.now()) / 1000))
      setRestant(secondes)
      if (secondes === 0) charger()
    }
    tic()
    const minuteur = window.setInterval(tic, 1000)
    return () => window.clearInterval(minuteur)
  }, [commande, charger])

  async function payer(resultat: 'accepte' | 'refuse') {
    if (!commande?.psp_session) return
    setEtat('traitement')
    setErreur(null)
    try {
      const reponse = await api<{ statut: string }>(`/api/paiement-simule/${commande.psp_session}`, {
        method: 'POST',
        body: JSON.stringify({ resultat }),
      })
      if (reponse.statut === 'payee') navigate(`/commande/${commande.id}`, { replace: true })
      else setEtat('refuse')
    } catch (e) {
      setErreur((e as ErreurApi).message)
      setEtat('attente')
      charger()
    }
  }

  async function annuler() {
    if (!commande) return
    await api(`/api/commandes/${commande.id}`, { method: 'DELETE' }).catch(() => undefined)
    navigate(`/seances/${commande.seance.id}`, { replace: true })
  }

  if (erreur && !commande)
    return (
      <section className="page page--etroite etat-vide">
        <h1>Commande introuvable</h1>
        <p>{erreur}</p>
      </section>
    )
  if (!commande) return <div className="page page--etroite squelette squelette--paiement" aria-busy="true" />

  const seance = commande.seance
  const terminee = commande.statut === 'expiree' || commande.statut === 'annulee'
  const minutes = Math.floor(restant / 60)
  const secondes = String(restant % 60).padStart(2, '0')

  return (
    <div className={`paiement${borne ? ' paiement--borne' : ''}`}>
      <section className="paiement__recap">
        <p className="paiement__reference">Commande {commande.reference}</p>
        <h1>{seance.film.titre}</h1>
        <p className="paiement__seance">
          <span className="capitalise">{dateLongue(seance.debut)}</span> à {heure(seance.debut)}, {seance.salle.nom},{' '}
          {seance.version}
        </p>
        <ul className="paiement__lignes">
          {commande.lignes.map((l) => (
            <li key={l.siege_id}>
              <span className="paiement__place">{place(l)}</span>
              <span>{l.libelle}</span>
              <span>{euros(l.prix_centimes)}</span>
            </li>
          ))}
        </ul>
        <p className="paiement__total">
          <span>À payer</span>
          <strong>{euros(commande.montant_centimes)}</strong>
        </p>
      </section>

      <section className="terminal" aria-live="polite">
        {terminee ? (
          <>
            <h2>Délai dépassé</h2>
            <p>Vos places ont été remises en vente. Vous pouvez recommencer votre réservation.</p>
            <a className="bouton bouton--plein" href={`/seances/${seance.id}`}>
              Choisir à nouveau
            </a>
          </>
        ) : (
          <>
            <div className="terminal__entete">
              <span>Paiement sécurisé</span>
              <span className={`terminal__minuteur${restant < 60 ? ' terminal__minuteur--urgent' : ''}`}>
                {minutes}:{secondes}
              </span>
            </div>
            <p className="terminal__montant">{euros(commande.montant_centimes)}</p>
            <p className="terminal__consigne">
              {borne
                ? 'Présentez votre carte sur le terminal de paiement de la borne.'
                : 'Le paiement est traité par le prestataire du cinéma. Aucune donnée de carte ne passe par CinetINT.'}
            </p>
            {etat === 'refuse' && (
              <p className="message message--alerte" role="alert">
                Paiement refusé par la banque. Vos places restent bloquées jusqu’à la fin du délai.
              </p>
            )}
            {erreur && (
              <p className="message message--alerte" role="alert">
                {erreur}
              </p>
            )}
            <button
              type="button"
              className="bouton bouton--plein"
              disabled={etat === 'traitement'}
              onClick={() => payer('accepte')}
            >
              {etat === 'traitement' ? 'Paiement en cours…' : `Payer ${euros(commande.montant_centimes)}`}
            </button>
            <div className="terminal__secondaire">
              <button type="button" className="lien" disabled={etat === 'traitement'} onClick={() => payer('refuse')}>
                Simuler un refus de la banque
              </button>
              <button type="button" className="lien" onClick={annuler}>
                Annuler et libérer les places
              </button>
            </div>
            <p className="terminal__demo">Prestataire de paiement simulé pour la démonstration.</p>
          </>
        )}
      </section>
    </div>
  )
}
