import { useEffect, useState } from 'react'

import { useAdmin } from './contexte.ts'

type Controle = {
  id: number
  moment: string
  resultat: string
  poste: string
  film: string | null
  place: string | null
  reference_billet: string | null
}

const RESULTATS: Record<string, string> = {
  accepte: 'Entrée validée',
  deja_utilise: 'Déjà utilisé',
  rembourse: 'Billet remboursé',
  inconnu: 'Billet inconnu',
  signature_invalide: 'Signature invalide',
}

export default function Controles() {
  const { appel } = useAdmin()
  const [lignes, setLignes] = useState<Controle[] | null>(null)

  useEffect(() => {
    const charger = () => appel<Controle[]>('/api/admin/controles?limite=60').then(setLignes).catch(() => undefined)
    charger()
    const minuteur = window.setInterval(charger, 5000)
    return () => window.clearInterval(minuteur)
  }, [appel])

  if (!lignes) return <div className="squelette squelette--tableau" aria-busy="true" />

  const refus = lignes.filter((l) => l.resultat !== 'accepte').length

  return (
    <div className="gestion">
      <section className="gestion__bloc">
        <h1>Journal du contrôle d’entrée</h1>
        <p className="gestion__aide">
          {lignes.length} derniers passages, dont {refus} refusés. Les tentatives de repasse et les faux billets apparaissent
          ici en temps réel.
        </p>
        {lignes.length === 0 ? (
          <p className="etat-vide">Aucun billet scanné pour l’instant.</p>
        ) : (
          <table className="tableau">
            <thead>
              <tr>
                <th>Heure</th>
                <th>Résultat</th>
                <th>Billet</th>
                <th>Poste</th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((l) => (
                <tr key={l.id}>
                  <td>{new Date(l.moment).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</td>
                  <td>
                    <span className={`statut statut--${l.resultat === 'accepte' ? 'valide' : 'refus'}`}>{RESULTATS[l.resultat] ?? l.resultat}</span>
                  </td>
                  <td>{l.film ? `${l.place}, ${l.film}` : <span className="tableau__doux">non identifié</span>}</td>
                  <td className="tableau__doux">{l.poste || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
