import { type FormEvent, useEffect, useState } from 'react'

import { ErreurApi } from '../../api.ts'
import { useAdmin } from './contexte.ts'

type Parametre = { cle: string; valeur: number; libelle: string }

export default function Parametres() {
  const { appel } = useAdmin()
  const [valeurs, setValeurs] = useState<Parametre[] | null>(null)
  const [message, setMessage] = useState<{ type: 'ok' | 'alerte'; texte: string } | null>(null)
  const [recalcul, setRecalcul] = useState<string | null>(null)

  useEffect(() => {
    appel<Parametre[]>('/api/admin/parametres').then(setValeurs).catch(() => undefined)
  }, [appel])

  async function enregistrer(e: FormEvent) {
    e.preventDefault()
    if (!valeurs) return
    try {
      const corps = Object.fromEntries(valeurs.map((p) => [p.cle, p.valeur]))
      setValeurs(await appel<Parametre[]>('/api/admin/parametres', { method: 'PUT', body: JSON.stringify(corps) }))
      setMessage({ type: 'ok', texte: 'Réglages enregistrés, ils valent pour les prochaines commandes.' })
    } catch (err) {
      setMessage({ type: 'alerte', texte: (err as ErreurApi).message })
    }
  }

  async function recalculer() {
    const { seances } = await appel<{ seances: number }>('/api/admin/remplissage/recalcul', { method: 'POST' })
    setRecalcul(`Compteurs recalculés depuis la base pour ${seances} séances.`)
  }

  if (!valeurs) return <div className="squelette squelette--tableau" aria-busy="true" />

  return (
    <div className="gestion">
      <section className="gestion__bloc">
        <h1>Réglages de la vente</h1>
        <form className="formulaire" onSubmit={enregistrer}>
          <div className="formulaire__grille">
            {valeurs.map((p) => (
              <div className="champ" key={p.cle}>
                <label htmlFor={p.cle}>{p.libelle}</label>
                <input
                  id={p.cle}
                  type="number"
                  min={p.cle === 'places_max' ? 1 : 0}
                  max={10000}
                  required
                  value={p.valeur}
                  onChange={(e) => setValeurs(valeurs.map((x) => (x.cle === p.cle ? { ...x, valeur: Number(e.target.value) } : x)))}
                />
              </div>
            ))}
          </div>
          {message && (
            <p className={`message message--${message.type}`} role="status">
              {message.texte}
            </p>
          )}
          <div className="formulaire__actions">
            <button className="bouton bouton--plein">Enregistrer</button>
          </div>
        </form>
      </section>

      <section className="gestion__bloc">
        <h2>Compteurs de remplissage</h2>
        <p className="gestion__aide">
          Les compteurs affichés en direct sont gardés en cache dans Redis. En cas de doute, ils se recalculent à partir des
          billets enregistrés en base.
        </p>
        <div className="formulaire__actions">
          <button type="button" className="bouton" onClick={recalculer}>
            Recalculer les compteurs
          </button>
          {recalcul && <p className="gestion__aide">{recalcul}</p>}
        </div>
      </section>
    </div>
  )
}
