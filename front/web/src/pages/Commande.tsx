import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router'

import { api, ErreurApi, urlApi, urlQr } from '../api.ts'
import { estBorne } from '../borne.ts'
import { dateHeure, dateLongue, euros, heure, place } from '../format.ts'
import type { Billet, Commande as CommandeT } from '../types.ts'

export default function Commande() {
  const { id } = useParams()
  const borne = estBorne()
  const [commande, setCommande] = useState<CommandeT | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'ok' | 'alerte'; texte: string } | null>(null)
  const [aRembourser, setARembourser] = useState<Billet | null>(null)
  const [copie, setCopie] = useState(false)

  const charger = useCallback(async () => {
    try {
      setCommande(await api<CommandeT>(`/api/commandes/${id}`))
    } catch (e) {
      setErreur((e as ErreurApi).message)
    }
  }, [id])

  useEffect(() => {
    charger()
  }, [charger])

  // à la borne, l'écran revient à la programmation au bout d'une minute et demie
  useEffect(() => {
    if (!borne) return
    const minuteur = window.setTimeout(() => window.location.assign('/borne'), 90_000)
    return () => window.clearTimeout(minuteur)
  }, [borne])

  async function rembourser(billet: Billet) {
    if (!commande) return
    try {
      const maj = await api<CommandeT>(`/api/billets/${billet.id}/remboursement`, {
        method: 'POST',
        body: JSON.stringify({ commande_id: commande.id }),
      })
      setCommande(maj)
      setMessage({ type: 'ok', texte: `Place ${place(billet)} remboursée : ${euros(billet.prix_centimes)} reviennent sur votre carte.` })
    } catch (e) {
      setMessage({ type: 'alerte', texte: (e as ErreurApi).message })
    } finally {
      setARembourser(null)
    }
  }

  async function copierLien() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopie(true)
      window.setTimeout(() => setCopie(false), 2500)
    } catch {
      setCopie(false)
    }
  }

  if (erreur)
    return (
      <section className="page page--etroite etat-vide">
        <h1>Commande introuvable</h1>
        <p>{erreur}</p>
      </section>
    )
  if (!commande) return <div className="page squelette squelette--billets" aria-busy="true" />

  if (commande.statut !== 'payee')
    return (
      <section className="page page--etroite etat-vide">
        <h1>Commande non payée</h1>
        <p>Cette commande n’a pas été réglée, aucun billet n’a été émis.</p>
        <a className="bouton bouton--plein" href={`/seances/${commande.seance.id}`}>
          Revenir à la séance
        </a>
      </section>
    )

  const seance = commande.seance
  const limite = new Date(commande.remboursable_jusqua)
  const encoreRemboursable = Date.now() < limite.getTime()
  const valides = commande.billets.filter((b) => b.statut === 'valide')

  return (
    <div className="billets page">
      <header className="billets__entete">
        <p className="billets__confirmation">Paiement accepté</p>
        <h1>Vos billets</h1>
        <p className="billets__seance">
          {seance.film.titre}, <span className="capitalise">{dateLongue(seance.debut)}</span> à {heure(seance.debut)},{' '}
          {seance.salle.nom}
        </p>
        <div className="billets__reference">
          <span>Référence</span>
          <strong>{commande.reference}</strong>
        </div>
        <div className="billets__actions">
          {valides.length > 0 && (
            <a className="bouton bouton--plein" href={urlApi(`/api/commandes/${commande.id}/billets.pdf`)}>
              Télécharger en PDF
            </a>
          )}
          {borne ? (
            <button type="button" className="bouton" onClick={() => window.print()}>
              Imprimer
            </button>
          ) : (
            <button type="button" className="bouton" onClick={copierLien}>
              {copie ? 'Lien copié' : 'Copier le lien de la commande'}
            </button>
          )}
        </div>
        <p className="billets__note">
          Pas de compte : gardez ce lien ou le PDF. Chaque billet est valable pour une seule entrée, montrez son code à
          l’entrée de la salle.
        </p>
      </header>

      {message && (
        <p className={`message message--${message.type}`} role="status">
          {message.texte}
        </p>
      )}

      <ol className="billets__liste">
        {commande.billets.map((b) => (
          <li key={b.id} className={`billet billet--${b.statut}`}>
            <div className="billet__corps">
              <p className="billet__film">{seance.film.titre}</p>
              <p className="billet__date capitalise">{dateHeure(seance.debut)}</p>
              <dl className="billet__infos">
                <div>
                  <dt>Salle</dt>
                  <dd>{seance.salle.nom.replace('Salle ', '')}</dd>
                </div>
                <div>
                  <dt>Place</dt>
                  <dd>{place(b)}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{seance.version}</dd>
                </div>
              </dl>
              <p className="billet__tarif">
                {b.libelle_tarif} <strong>{euros(b.prix_centimes)}</strong>
              </p>
              {seance.evenement && <p className="billet__evenement">{seance.evenement.nom}</p>}
            </div>
            <div className="billet__talon">
              {b.statut === 'valide' && b.jeton ? (
                <img className="billet__qr" src={urlQr(b.jeton)} alt={`Code du billet, place ${place(b)}`} width="180" height="180" />
              ) : (
                <p className="billet__statut">
                  {b.statut === 'utilise' ? 'Utilisé' : 'Remboursé'}
                  <span>
                    {b.statut === 'utilise' && b.utilise_le && `le ${dateHeure(b.utilise_le)}`}
                    {b.statut === 'rembourse' && b.rembourse_le && `le ${dateHeure(b.rembourse_le)}`}
                  </span>
                </p>
              )}
              {b.statut === 'valide' && !borne && encoreRemboursable && (
                <button type="button" className="lien" onClick={() => setARembourser(b)}>
                  Rembourser ce billet
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>

      {!borne && valides.length > 0 && (
        <p className="billets__remboursement">
          {encoreRemboursable
            ? `Remboursement possible jusqu’au ${dateHeure(commande.remboursable_jusqua)}. Un billet scanné à l’entrée n’est plus remboursable.`
            : 'Le délai de remboursement est passé pour cette séance.'}
        </p>
      )}

      {aRembourser && (
        <div className="dialogue" role="dialog" aria-modal="true" aria-labelledby="titre-remboursement">
          <div className="dialogue__boite">
            <h2 id="titre-remboursement">Rembourser la place {place(aRembourser)} ?</h2>
            <p>
              {euros(aRembourser.prix_centimes)} seront recrédités sur la carte utilisée. Le billet sera annulé et la place
              remise en vente.
            </p>
            <div className="dialogue__actions">
              <button type="button" className="bouton" onClick={() => setARembourser(null)}>
                Garder le billet
              </button>
              <button type="button" className="bouton bouton--danger" onClick={() => rembourser(aRembourser)}>
                Rembourser
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
