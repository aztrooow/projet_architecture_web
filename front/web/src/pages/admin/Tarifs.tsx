import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { ErreurApi } from '../../api.ts'
import { euros } from '../../format.ts'
import type { Evenement } from '../../types.ts'
import { useAdmin } from './contexte.ts'

type Regle = {
  id: number
  libelle: string
  prix_centimes: number
  priorite: number
  jours: number[] | null
  type_production: string | null
  categorie: string | null
  evenement_id: number | null
  actif: boolean
}
type Categorie = { code: string; libelle: string; ordre: number; actif: boolean }

const JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const REGLE_VIDE = { libelle: '', prix: '', priorite: '30', jours: [] as number[], type_production: '', categorie: '', evenement_id: '', actif: true }

export default function Tarifs() {
  const { appel } = useAdmin()
  const [regles, setRegles] = useState<Regle[]>([])
  const [categories, setCategories] = useState<Categorie[]>([])
  const [evenements, setEvenements] = useState<Evenement[]>([])
  const [regle, setRegle] = useState<typeof REGLE_VIDE & { id?: number }>(REGLE_VIDE)
  const [evenement, setEvenement] = useState({ nom: '', description: '' })
  const [categorie, setCategorie] = useState({ code: '', libelle: '' })
  const [message, setMessage] = useState<{ type: 'ok' | 'alerte'; texte: string } | null>(null)

  const charger = useCallback(async () => {
    const [r, c, e] = await Promise.all([
      appel<Regle[]>('/api/admin/tarifs'),
      appel<Categorie[]>('/api/admin/categories'),
      appel<Evenement[]>('/api/admin/evenements'),
    ])
    setRegles(r)
    setCategories(c)
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

  function enregistrerRegle(e: FormEvent) {
    e.preventDefault()
    const corps = JSON.stringify({
      libelle: regle.libelle,
      prix_centimes: Math.round(Number(regle.prix.replace(',', '.')) * 100),
      priorite: Number(regle.priorite),
      jours: regle.jours.length ? regle.jours : null,
      type_production: regle.type_production || null,
      categorie: regle.categorie || null,
      evenement_id: regle.evenement_id ? Number(regle.evenement_id) : null,
      actif: regle.actif,
    })
    agir(
      () => appel(regle.id ? `/api/admin/tarifs/${regle.id}` : '/api/admin/tarifs', { method: regle.id ? 'PUT' : 'POST', body: corps }),
      regle.id ? 'Règle mise à jour.' : 'Règle ajoutée : elle s’applique dès maintenant aux nouvelles commandes.',
    ).then((ok) => ok && setRegle(REGLE_VIDE))
  }

  function basculerJour(j: number) {
    setRegle((r) => ({ ...r, jours: r.jours.includes(j) ? r.jours.filter((x) => x !== j) : [...r.jours, j].sort() }))
  }

  const nomCategorie = (code: string | null) => categories.find((c) => c.code === code)?.libelle ?? code
  const nomEvenement = (id: number | null) => evenements.find((e) => e.id === id)?.nom

  function criteres(r: Regle) {
    const morceaux = []
    if (r.jours?.length) morceaux.push(r.jours.map((j) => JOURS[j]).join(' '))
    if (r.type_production) morceaux.push(r.type_production === '3d' ? '3D' : 'Art et essai')
    if (r.categorie) morceaux.push(nomCategorie(r.categorie))
    if (r.evenement_id) morceaux.push(nomEvenement(r.evenement_id))
    return morceaux.join(', ') || 'Toutes les places'
  }

  return (
    <div className="gestion">
      {message && (
        <p className={`message message--${message.type}`} role="status">
          {message.texte}
        </p>
      )}

      <section className="gestion__bloc">
        <h1>Grille tarifaire</h1>
        <p className="gestion__aide">
          Pour chaque place, la règle applicable de plus haute priorité l’emporte. Une règle d’évènement avec une priorité
          très haute impose un tarif unique à toutes les places de la séance.
        </p>
        <table className="tableau">
          <thead>
            <tr>
              <th>Règle</th>
              <th>S’applique à</th>
              <th>Priorité</th>
              <th>Prix</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {regles.map((r) => (
              <tr key={r.id} className={r.actif ? '' : 'tableau__inactif'}>
                <td>{r.libelle}</td>
                <td className="tableau__doux">{criteres(r)}</td>
                <td>{r.priorite}</td>
                <td className="tableau__prix">{euros(r.prix_centimes)}</td>
                <td className="tableau__actions">
                  <button
                    type="button"
                    className="lien"
                    onClick={() =>
                      setRegle({
                        id: r.id,
                        libelle: r.libelle,
                        prix: (r.prix_centimes / 100).toFixed(2).replace('.', ','),
                        priorite: String(r.priorite),
                        jours: r.jours ?? [],
                        type_production: r.type_production ?? '',
                        categorie: r.categorie ?? '',
                        evenement_id: r.evenement_id ? String(r.evenement_id) : '',
                        actif: r.actif,
                      })
                    }
                  >
                    Modifier
                  </button>
                  <button type="button" className="lien" onClick={() => agir(() => appel(`/api/admin/tarifs/${r.id}`, { method: 'DELETE' }), 'Règle supprimée.')}>
                    Supprimer
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="gestion__bloc">
        <h2>{regle.id ? `Modifier « ${regle.libelle} »` : 'Nouvelle règle'}</h2>
        <form className="formulaire" onSubmit={enregistrerRegle}>
          <div className="formulaire__grille">
            <div className="champ">
              <label htmlFor="r-libelle">Libellé affiché au spectateur</label>
              <input id="r-libelle" required value={regle.libelle} onChange={(e) => setRegle({ ...regle, libelle: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="r-prix">Prix (€)</label>
              <input id="r-prix" required inputMode="decimal" pattern="\d+([.,]\d{1,2})?" value={regle.prix} onChange={(e) => setRegle({ ...regle, prix: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="r-priorite">Priorité</label>
              <input id="r-priorite" type="number" required value={regle.priorite} onChange={(e) => setRegle({ ...regle, priorite: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="r-type">Type de film</label>
              <select id="r-type" value={regle.type_production} onChange={(e) => setRegle({ ...regle, type_production: e.target.value })}>
                <option value="">Tous</option>
                <option value="standard">Standard</option>
                <option value="3d">3D</option>
                <option value="art_essai">Art et essai</option>
              </select>
            </div>
            <div className="champ">
              <label htmlFor="r-categorie">Catégorie de spectateur</label>
              <select id="r-categorie" value={regle.categorie} onChange={(e) => setRegle({ ...regle, categorie: e.target.value })}>
                <option value="">Toutes</option>
                {categories.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.libelle}
                  </option>
                ))}
              </select>
            </div>
            <div className="champ">
              <label htmlFor="r-evenement">Évènement</label>
              <select id="r-evenement" value={regle.evenement_id} onChange={(e) => setRegle({ ...regle, evenement_id: e.target.value })}>
                <option value="">Aucun</option>
                {evenements.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.nom}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <fieldset className="jours-semaine">
            <legend>Jours (aucun = tous les jours)</legend>
            {JOURS.map((j, i) => (
              <label key={j} className="case">
                <input type="checkbox" checked={regle.jours.includes(i)} onChange={() => basculerJour(i)} />
                {j}
              </label>
            ))}
          </fieldset>
          <label className="case">
            <input type="checkbox" checked={regle.actif} onChange={(e) => setRegle({ ...regle, actif: e.target.checked })} />
            Règle active
          </label>
          <div className="formulaire__actions">
            <button className="bouton bouton--plein">{regle.id ? 'Enregistrer' : 'Ajouter la règle'}</button>
            {regle.id && (
              <button type="button" className="lien" onClick={() => setRegle(REGLE_VIDE)}>
                Annuler
              </button>
            )}
          </div>
        </form>
      </section>

      <div className="gestion__colonnes">
        <section className="gestion__bloc">
          <h2>Évènements</h2>
          <ul className="liste-simple">
            {evenements.map((e) => (
              <li key={e.id}>
                <strong>{e.nom}</strong>
                <span className="tableau__doux">{e.description}</span>
              </li>
            ))}
          </ul>
          <form
            className="formulaire"
            onSubmit={(e) => {
              e.preventDefault()
              agir(() => appel('/api/admin/evenements', { method: 'POST', body: JSON.stringify(evenement) }), 'Évènement créé. Ajoutez-lui une règle de tarif et des séances.').then(
                (ok) => ok && setEvenement({ nom: '', description: '' }),
              )
            }}
          >
            <div className="champ">
              <label htmlFor="e-nom">Nom</label>
              <input id="e-nom" required value={evenement.nom} onChange={(e) => setEvenement({ ...evenement, nom: e.target.value })} />
            </div>
            <div className="champ">
              <label htmlFor="e-description">Description</label>
              <textarea id="e-description" rows={2} value={evenement.description} onChange={(e) => setEvenement({ ...evenement, description: e.target.value })} />
            </div>
            <button className="bouton">Créer l’évènement</button>
          </form>
        </section>

        <section className="gestion__bloc">
          <h2>Catégories de spectateurs</h2>
          <ul className="liste-simple">
            {categories.map((c) => (
              <li key={c.code}>
                <strong>{c.libelle}</strong>
                <label className="case">
                  <input
                    type="checkbox"
                    checked={c.actif}
                    onChange={() =>
                      agir(
                        () => appel(`/api/admin/categories/${c.code}`, { method: 'PUT', body: JSON.stringify({ ...c, actif: !c.actif }) }),
                        c.actif ? `${c.libelle} n’est plus proposée.` : `${c.libelle} est de nouveau proposée.`,
                      )
                    }
                  />
                  Proposée à la vente
                </label>
              </li>
            ))}
          </ul>
          <form
            className="formulaire"
            onSubmit={(e) => {
              e.preventDefault()
              agir(
                () =>
                  appel(`/api/admin/categories/${categorie.code}`, {
                    method: 'PUT',
                    body: JSON.stringify({ ...categorie, ordre: categories.length, actif: true }),
                  }),
                'Catégorie ajoutée.',
              ).then((ok) => ok && setCategorie({ code: '', libelle: '' }))
            }}
          >
            <div className="formulaire__grille">
              <div className="champ">
                <label htmlFor="c-code">Code</label>
                <input id="c-code" required pattern="[a-z_]{2,20}" placeholder="abonne" value={categorie.code} onChange={(e) => setCategorie({ ...categorie, code: e.target.value })} />
              </div>
              <div className="champ">
                <label htmlFor="c-libelle">Libellé</label>
                <input id="c-libelle" required placeholder="Abonné" value={categorie.libelle} onChange={(e) => setCategorie({ ...categorie, libelle: e.target.value })} />
              </div>
            </div>
            <button className="bouton">Ajouter la catégorie</button>
          </form>
        </section>
      </div>
    </div>
  )
}
