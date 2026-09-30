import type { CSSProperties } from 'react'

import type { Plan, Siege } from '../types.ts'

type Props = {
  plan: Plan
  choix: Map<number, string>
  onBasculer: (siege: Siege) => void
}

export default function PlanSalle({ plan, choix, onBasculer }: Props) {
  // une étiquette de rang de chaque côté, comme sur les plaques au bout des rangées
  const rangs = new Map<number, string>()
  for (const s of plan.sieges) rangs.set(s.y, s.rang)
  const style = { '--colonnes': plan.largeur + 2 } as CSSProperties

  return (
    <div className="plan">
      <div className="plan__ecran" aria-hidden="true">
        <span>Écran</span>
      </div>
      <div className="plan__defilement">
        <div className="plan__grille" style={style} role="group" aria-label="Plan de la salle">
          {[...rangs].map(([y, rang]) => [
            <span key={`g${y}`} className="plan__rang" style={{ gridRow: y + 1, gridColumn: 1 }} aria-hidden="true">
              {rang}
            </span>,
            <span
              key={`d${y}`}
              className="plan__rang"
              style={{ gridRow: y + 1, gridColumn: plan.largeur + 2 }}
              aria-hidden="true"
            >
              {rang}
            </span>,
          ])}
          {plan.sieges.map((s) => {
            const choisi = choix.has(s.id)
            const pris = s.etat === 'vendu' || s.etat === 'verrouille'
            const classes = ['siege', choisi && 'siege--choisi', pris && 'siege--pris', s.pmr && 'siege--pmr']
            return (
              <button
                key={s.id}
                type="button"
                className={classes.filter(Boolean).join(' ')}
                style={{ gridRow: s.y + 1, gridColumn: s.x + 2 }}
                disabled={pris}
                aria-pressed={choisi}
                title={`${s.rang}${s.numero}`}
                aria-label={`Rang ${s.rang}, place ${s.numero}${s.pmr ? ', accessible en fauteuil' : ''}${pris ? ', indisponible' : ''}`}
                onClick={() => onBasculer(s)}
              />
            )
          })}
        </div>
      </div>
      <ul className="plan__legende">
        <li>
          <span className="siege siege--exemple" /> Libre
        </li>
        <li>
          <span className="siege siege--exemple siege--choisi" /> Votre choix
        </li>
        <li>
          <span className="siege siege--exemple siege--pris" /> Indisponible
        </li>
        <li>
          <span className="siege siege--exemple siege--pmr" /> Accessible en fauteuil
        </li>
      </ul>
    </div>
  )
}
