import { type FormEvent, useState } from 'react'

import { ErreurApi } from '../../api.ts'
import { dateHeure, euros, place } from '../../format.ts'
import type { Commande } from '../../types.ts'
import { useAdmin } from './contexte.ts'

const STATUTS = { valide: 'Valide', utilise: 'Utilisé', rembourse: 'Remboursé' }

export default function Billets() {
  const { appel } = useAdmin()
  const [reference, setReference] = useState('')
  const [commande, setCommande] = useState<Commande | null>(null)
  const [message, setMessage] = useState<{ type: 'ok' | 'alerte'; texte: string } | null>(null)

  async function chercher(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    try {
      setCommande(await appel<Commande>(`/api/admin/commandes?reference=${encodeURIComponent(reference.trim())}`))
    } catch (err) {
      setCommande(null)
      setMessage({ type: 'alerte', texte: (err as ErreurApi).message })
    }
  }

  async function rembourser(billetId: string) {
    setMessage(null)
    try {
      setCommande(await appel<Commande>(`/api/admin/billets/${billetId}/remboursement`, { method: 'POST' }))
      setMessage({ type: 'ok', texte: 'Billet remboursé, la place est de nouveau en vente.' })
    } catch (err) {
      setMessage({ type: 'alerte', texte: (err as ErreurApi).message })
    }
  }

  return (
    <div className="gestion">
      <section className="gestion__bloc">
        <h1>Retrouver une commande</h1>
        <p className="gestion__aide">
          Le gérant peut rembourser un billet même après le délai accordé en ligne. Un billet déjà scanné à l’entrée reste
          non remboursable.
        </p>
        <form className="formulaire formulaire--ligne" onSubmit={chercher}>
          <div className="champ">
            <label htmlFor="reference">Référence</label>
            <input id="reference" required placeholder="CIN-7K2QXM" value={reference} onChange={(e) => setReference(e.target.value)} />
          </div>
          <button className="bouton bouton--plein">Chercher</button>
        </form>
      </section>

      {message && (
        <p className={`message message--${message.type}`} role="status">
          {message.texte}
        </p>
      )}

      {commande && (
        <section className="gestion__bloc">
          <h2>
            {commande.reference}, {commande.seance.film.titre}
          </h2>
          <p className="gestion__aide capitalise">
            {dateHeure(commande.seance.debut)}, {commande.seance.salle.nom}, vente {commande.canal === 'borne' ? 'à la borne' : 'en ligne'},{' '}
            {euros(commande.montant_centimes)}
          </p>
          <table className="tableau">
            <thead>
              <tr>
                <th>Place</th>
                <th>Tarif</th>
                <th>Prix</th>
                <th>Statut</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {commande.billets.map((b) => (
                <tr key={b.id}>
                  <td>{place(b)}</td>
                  <td>{b.libelle_tarif}</td>
                  <td className="tableau__prix">{euros(b.prix_centimes)}</td>
                  <td>
                    <span className={`statut statut--${b.statut}`}>{STATUTS[b.statut]}</span>
                    {b.utilise_le && <span className="tableau__doux"> {dateHeure(b.utilise_le)}</span>}
                  </td>
                  <td>
                    {b.statut === 'valide' && (
                      <button type="button" className="bouton bouton--petit bouton--danger" onClick={() => rembourser(b.id)}>
                        Rembourser
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
