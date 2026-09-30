import type { CSSProperties } from 'react'

import type { Film } from '../types.ts'

// le CDN des affiches redimensionne à la volée : .../c_215_290/img/...
const variante = (url: string, taille: string) => url.replace(/(acsta\.net\/)/, `$1${taille}/`)

export default function Affiche({ film, taille = 'moyenne' }: { film: Film; taille?: 'petite' | 'moyenne' }) {
  if (film.affiche_url)
    return (
      <img
        className={`affiche affiche--photo affiche--${taille}`}
        src={variante(film.affiche_url, taille === 'petite' ? 'c_215_290' : 'c_310_420')}
        alt={`Affiche du film ${film.titre}`}
        width={taille === 'petite' ? 84 : 310}
        height={taille === 'petite' ? 114 : 420}
      />
    )
  // sans affiche (séance évènement), une affiche typographique dans la même charte
  return (
    <div className={`affiche affiche--${taille}`} style={{ '--teinte': film.couleur } as CSSProperties} aria-hidden="true">
      <span className="affiche__titre">{film.titre}</span>
      <span className="affiche__meta">
        {film.realisation.split(',')[0]}
        {film.annee ? `, ${film.annee}` : ''}
      </span>
    </div>
  )
}
