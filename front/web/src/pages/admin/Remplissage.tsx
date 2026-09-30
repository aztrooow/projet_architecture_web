import { useCallback, useEffect, useState } from 'react'

import { urlApi } from '../../api.ts'
import { dateLongue, euros, heure } from '../../format.ts'
import { useAdmin } from './contexte.ts'

type Ligne = {
  seance_id: number
  debut: string
  film: string
  salle: string
  version: string
  evenement: string | null
  capacite: number
  vendus: number
}

type Resume = {
  billets_vendus: number
  recette_centimes: number
  seances: number
  taux_remplissage: number
  entrees: number
}

export default function Remplissage() {
  const { appel, jeton } = useAdmin()
  const [lignes, setLignes] = useState<Ligne[] | null>(null)
  const [resume, setResume] = useState<Resume | null>(null)
  const [enDirect, setEnDirect] = useState(false)
  const [maj, setMaj] = useState<number | null>(null)

  const charger = useCallback(async () => {
    const [l, r] = await Promise.all([appel<Ligne[]>('/api/admin/remplissage?jours=2'), appel<Resume>('/api/admin/resume')])
    setLignes(l)
    setResume(r)
  }, [appel])

  useEffect(() => {
    charger().catch(() => undefined)
  }, [charger])

  // chaque vente ou remboursement, sur n'importe quelle instance de l'API, arrive ici
  useEffect(() => {
    const flux = new EventSource(urlApi(`/api/admin/flux?jeton=${encodeURIComponent(jeton)}`))
    flux.onopen = () => setEnDirect(true)
    flux.onerror = () => setEnDirect(false)
    flux.onmessage = (message) => {
      const { seance_id, vendus } = JSON.parse(message.data) as { seance_id: number; vendus: number }
      setLignes((l) => l?.map((x) => (x.seance_id === seance_id ? { ...x, vendus } : x)) ?? l)
      setMaj(seance_id)
    }
    const resume = window.setInterval(() => appel<Resume>('/api/admin/resume').then(setResume).catch(() => undefined), 20_000)
    return () => {
      flux.close()
      window.clearInterval(resume)
    }
  }, [appel, jeton])

  if (!lignes || !resume) return <div className="squelette squelette--tableau" aria-busy="true" />

  const parJour = new Map<string, Ligne[]>()
  for (const l of lignes) {
    const cle = dateLongue(l.debut)
    parJour.set(cle, [...(parJour.get(cle) ?? []), l])
  }

  return (
    <div className="remplissage">
      <section className="indicateurs" aria-label="Chiffres du jour">
        <p>
          <span className="indicateurs__valeur">{resume.taux_remplissage.toLocaleString('fr-FR')} %</span>
          <span className="indicateurs__legende">remplissage des séances du jour</span>
        </p>
        <p>
          <span className="indicateurs__valeur">{resume.billets_vendus.toLocaleString('fr-FR')}</span>
          <span className="indicateurs__legende">billets vendus aujourd’hui</span>
        </p>
        <p>
          <span className="indicateurs__valeur">{euros(resume.recette_centimes)}</span>
          <span className="indicateurs__legende">recette du jour</span>
        </p>
        <p>
          <span className="indicateurs__valeur">{resume.entrees.toLocaleString('fr-FR')}</span>
          <span className="indicateurs__legende">entrées contrôlées</span>
        </p>
      </section>

      <div className="remplissage__titre">
        <h1>Remplissage par séance</h1>
        <p className={`direct${enDirect ? ' direct--actif' : ''}`}>{enDirect ? 'En direct' : 'Connexion au direct…'}</p>
      </div>

      {[...parJour].map(([jour, seances]) => (
        <section key={jour} className="remplissage__jour">
          <h2 className="capitalise">{jour}</h2>
          <ul className="jauges">
            {seances.map((s) => {
              const taux = Math.round((100 * s.vendus) / s.capacite)
              return (
                <li key={s.seance_id} className={`jauge${maj === s.seance_id ? ' jauge--maj' : ''}`}>
                  <span className="jauge__heure">{heure(s.debut)}</span>
                  <span className="jauge__film">
                    {s.film}
                    {s.evenement && <span className="badge badge--rouge">{s.evenement}</span>}
                  </span>
                  <span className="jauge__salle">
                    {s.salle}, {s.version}
                  </span>
                  <span className="jauge__barre" aria-hidden="true">
                    <span style={{ width: `${Math.min(100, taux)}%` }} className={taux >= 90 ? 'plein' : ''} />
                  </span>
                  <span className="jauge__chiffres">
                    <strong>{taux} %</strong> {s.vendus}/{s.capacite}
                  </span>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
