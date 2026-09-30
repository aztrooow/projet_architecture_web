import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { ErreurApi } from '../../api.ts'
import { dateLongue, duree, heure, typeProduction } from '../../format.ts'
import type { Evenement, Film } from '../../types.ts'
import { useAdmin } from './contexte.ts'

type SeanceAdmin = { seance_id: number; debut: string; film: string; salle: string; version: string; evenement: string | null; vendus: number; capacite: number }
type Salle = { id: number; nom: string; capacite: number }

const FILM_VIDE = { titre: '', realisation: '', annee: '', duree_min: '110', genre: '', synopsis: '', type_production: 'standard', couleur: '#7d1a1a' }

export default function Programmation() {
  const { appel } = useAdmin()
  const [seances, setSeances] = useState<SeanceAdmin[]>([])
  const [films, setFilms] = useState<Film[]>([])
  const [salles, setSalles] = useState<Salle[]>([])
  const [evenements, setEvenements] = useState<Evenement[]>([])
  const [message, setMessage] = useState<{ type: 'ok' | 'alerte'; texte: string } | null>(null)
  const [nouvelle, setNouvelle] = useState({ film_id: '', salle_id: '', debut: '', version: 'VF', evenement_id: '' })
  const [film, setFilm] = useState<typeof FILM_VIDE & { id?: number }>(FILM_VIDE)

  const charger = useCallback(async () => {
    const [s, f, sa, e] = await Promise.all([
      appel<SeanceAdmin[]>('/api/admin/seances?jours=14'),
      appel<Film[]>('/api/admin/films'),
      appel<Salle[]>('/api/admin/salles'),
      appel<Evenement[]>('/api/admin/evenements'),
    ])
    setSeances(s)
    setFilms(f)
    setSalles(sa)
    setEvenements(e)
  }, [appel])

  useEffect(() => {
    charger().catch(() => undefined)
  }, [charger])

  async function agir(action: () => Promise<unknown>, succes: string) {
    setMessage(null)
    try {
      await action()
      setMessage({ type: 'ok', texte: succes })
      await charger()
      return true
    } catch (e) {
      setMessage({ type: 'alerte', texte: (e as ErreurApi).message })
      return false
    }
  }

  function ajouterSeance(e: FormEvent) {
    e.preventDefault()
    agir(
      () =>
        appel('/api/admin/seances', {
          method: 'POST',
          body: JSON.stringify({
            film_id: Number(nouvelle.film_id),
            salle_id: Number(nouvelle.salle_id),
            debut: nouvelle.debut,
            version: nouvelle.version,
            evenement_id: nouvelle.evenement_id ? Number(nouvelle.evenement_id) : null,
          }),
        }),
      'Séance ajoutée à la programmation.',
    )
  }

  function enregistrerFilm(e: FormEvent) {
    e.preventDefault()
    const corps = JSON.stringify({ ...film, annee: film.annee ? Number(film.annee) : null, duree_min: Number(film.duree_min), id: undefined })
    agir(
      () => appel(film.id ? `/api/admin/films/${film.id}` : '/api/admin/films', { method: film.id ? 'PUT' : 'POST', body: corps }),
      film.id ? 'Film mis à jour.' : 'Film ajouté.',
    ).then((ok) => ok && setFilm(FILM_VIDE))
  }

  const parJour = new Map<string, SeanceAdmin[]>()
  for (const s of seances) {
    const cle = dateLongue(s.debut)
    parJour.set(cle, [...(parJour.get(cle) ?? []), s])
  }

  return (
    <div className="gestion">
      {message && (
        <p className={`message message--${message.type}`} role="status">
          {message.texte}
        </p>
      )}

      <section className="gestion__bloc">
        <h1>Ajouter une séance</h1>
        <form className="formulaire formulaire--ligne" onSubmit={ajouterSeance}>
          <div className="champ">
            <label htmlFor="s-film">Film</label>
            <select id="s-film" required value={nouvelle.film_id} onChange={(e) => setNouvelle({ ...nouvelle, film_id: e.target.value })}>
              <option value="">Choisir</option>
              {films.filter((f) => f.actif).map((f) => (
                <option key={f.id} value={f.id}>
                  {f.titre}
                </option>
              ))}
            </select>
          </div>
          <div className="champ">
            <label htmlFor="s-salle">Salle</label>
            <select id="s-salle" required value={nouvelle.salle_id} onChange={(e) => setNouvelle({ ...nouvelle, salle_id: e.target.value })}>
              <option value="">Choisir</option>
              {salles.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nom} ({s.capacite} places)
                </option>
              ))}
            </select>
          </div>
          <div className="champ">
            <label htmlFor="s-debut">Début</label>
            <input id="s-debut" type="datetime-local" required value={nouvelle.debut} onChange={(e) => setNouvelle({ ...nouvelle, debut: e.target.value })} />
          </div>
          <div className="champ">
            <label htmlFor="s-version">Version</label>
            <select id="s-version" value={nouvelle.version} onChange={(e) => setNouvelle({ ...nouvelle, version: e.target.value })}>
              <option>VF</option>
              <option>VOST</option>
            </select>
          </div>
          <div className="champ">
            <label htmlFor="s-evenement">Évènement</label>
            <select id="s-evenement" value={nouvelle.evenement_id} onChange={(e) => setNouvelle({ ...nouvelle, evenement_id: e.target.value })}>
              <option value="">Aucun</option>
              {evenements.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nom}
                </option>
              ))}
            </select>
          </div>
          <button className="bouton bouton--plein">Ajouter</button>
        </form>
      </section>

      <section className="gestion__bloc">
        <h2>Programmation des deux prochaines semaines</h2>
        {[...parJour].map(([jour, liste]) => (
          <details key={jour} className="gestion__jour">
            <summary>
              <span className="capitalise">{jour}</span> <span className="gestion__compte">{liste.length} séances</span>
            </summary>
            <table className="tableau">
              <thead>
                <tr>
                  <th>Heure</th>
                  <th>Film</th>
                  <th>Salle</th>
                  <th>Vendus</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {liste.map((s) => (
                  <tr key={s.seance_id}>
                    <td>{heure(s.debut)}</td>
                    <td>
                      {s.film} <span className="tableau__doux">{s.version}</span>
                      {s.evenement && <span className="badge badge--rouge">{s.evenement}</span>}
                    </td>
                    <td>{s.salle}</td>
                    <td>
                      {s.vendus}/{s.capacite}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="lien"
                        onClick={() => agir(() => appel(`/api/admin/seances/${s.seance_id}`, { method: 'DELETE' }), 'Séance supprimée.')}
                      >
                        Supprimer
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        ))}
      </section>

      <section className="gestion__bloc">
        <h2>{film.id ? `Modifier « ${film.titre} »` : 'Ajouter un film'}</h2>
        <form className="formulaire" onSubmit={enregistrerFilm}>
          <div className="formulaire__grille">
            <div className="champ">
              <label htmlFor="f-titre">Titre</label>
              <input id="f-titre" required value={film.titre} onChange={(e) => setFilm({ ...film, titre: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="f-real">Réalisation</label>
              <input id="f-real" value={film.realisation} onChange={(e) => setFilm({ ...film, realisation: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="f-annee">Année</label>
              <input id="f-annee" type="number" min="1890" max="2100" value={film.annee} onChange={(e) => setFilm({ ...film, annee: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="f-duree">Durée (minutes)</label>
              <input id="f-duree" type="number" min="1" max="600" required value={film.duree_min} onChange={(e) => setFilm({ ...film, duree_min: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="f-genre">Genre</label>
              <input id="f-genre" value={film.genre} onChange={(e) => setFilm({ ...film, genre: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="f-type">Type de production</label>
              <select id="f-type" value={film.type_production} onChange={(e) => setFilm({ ...film, type_production: e.target.value })}>
                <option value="standard">Standard</option>
                <option value="3d">3D</option>
                <option value="art_essai">Art et essai</option>
              </select>
            </div>
            <div className="champ">
              <label htmlFor="f-couleur">Couleur de l’affiche</label>
              <input id="f-couleur" type="color" value={film.couleur} onChange={(e) => setFilm({ ...film, couleur: e.target.value })} />
            </div>
          </div>
          <div className="champ">
            <label htmlFor="f-synopsis">Synopsis</label>
            <textarea id="f-synopsis" rows={3} value={film.synopsis} onChange={(e) => setFilm({ ...film, synopsis: e.target.value })} />
          </div>
          <div className="formulaire__actions">
            <button className="bouton bouton--plein">{film.id ? 'Enregistrer' : 'Ajouter le film'}</button>
            {film.id && (
              <button type="button" className="lien" onClick={() => setFilm(FILM_VIDE)}>
                Annuler
              </button>
            )}
          </div>
        </form>

        <ul className="liste-films">
          {films.map((f) => (
            <li key={f.id} className={f.actif ? '' : 'liste-films__retire'}>
              <span className="liste-films__pastille" style={{ background: f.couleur }} aria-hidden="true" />
              <span className="liste-films__titre">{f.titre}</span>
              <span className="tableau__doux">
                {duree(f.duree_min)}
                {typeProduction(f.type_production) && `, ${typeProduction(f.type_production)}`}
                {!f.actif && ', retiré de l’affiche'}
              </span>
              <span className="liste-films__actions">
                <button
                  type="button"
                  className="lien"
                  onClick={() =>
                    setFilm({
                      id: f.id,
                      titre: f.titre,
                      realisation: f.realisation,
                      annee: f.annee ? String(f.annee) : '',
                      duree_min: String(f.duree_min),
                      genre: f.genre,
                      synopsis: f.synopsis,
                      type_production: f.type_production,
                      couleur: f.couleur,
                    })
                  }
                >
                  Modifier
                </button>
                {f.actif && (
                  <button type="button" className="lien" onClick={() => agir(() => appel(`/api/admin/films/${f.id}`, { method: 'DELETE' }), `${f.titre} retiré de l’affiche.`)}>
                    Retirer
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
