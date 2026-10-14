import { useEffect, useState } from 'react'
import { Link, Route, Routes, useParams, useSearchParams } from 'react-router'

import type { ErreurApi } from '../../api.ts'
import { useAdmin } from './contexte.ts'

type Resume = { nom: string; titre: string; protegee: boolean; total: number; url: string }

type Colonne = { nom: string; type: string; cle_primaire: boolean; obligatoire: boolean; reference: string | null }

type Ligne = Record<string, unknown>

type Page = {
  table: string
  titre: string
  protegee: boolean
  total: number
  limite: number | null
  decalage: number
  colonnes: Colonne[]
  lignes: Ligne[]
}

const PAR_PAGE = 50

const DESCRIPTIONS: Record<string, string> = {
  salles: 'Les six salles et leur capacité.',
  sieges: 'Le plan de chaque salle, place par place.',
  films: 'Les films à l’affiche et leurs fiches.',
  evenements: 'Les manifestations à tarif unique.',
  seances: 'Un film, une salle, un horaire.',
  categories: 'Plein tarif, étudiant, moins de 14 ans, senior.',
  'regles-tarifaires': 'La grille de prix et ses priorités.',
  parametres: 'Les réglages de la vente.',
  commandes: 'Les achats, en ligne et à la borne.',
  billets: 'Un billet par place vendue, avec son statut.',
  controles: 'Le journal du contrôle d’entrée.',
  comptes: 'Le personnel (mots de passe jamais affichés).',
}

function Chargement() {
  return <div className="squelette squelette--tableau" aria-busy="true" />
}

function Erreur({ erreur }: { erreur: unknown }) {
  return (
    <p className="message message--alerte" role="alert">
      {(erreur as ErreurApi).message ?? 'Chargement impossible'}
    </p>
  )
}

// les colonnes d'une table pointent vers une autre table par « table.colonne » (clé étrangère)
const routeDeTable = (reference: string) => reference.split('.')[0].replace(/_/g, '-')

function Cellule({ valeur, colonne }: { valeur: unknown; colonne: Colonne }) {
  if (valeur === null || valeur === undefined) return <span className="tableau__doux">-</span>
  if (typeof valeur === 'boolean') return <>{valeur ? 'oui' : 'non'}</>
  if (colonne.type.startsWith('TIMESTAMP') && typeof valeur === 'string')
    return <>{new Date(valeur).toLocaleString('fr-FR', { timeZone: 'Europe/Paris' })}</>
  if (typeof valeur === 'object') return <code>{JSON.stringify(valeur)}</code>
  return <>{String(valeur)}</>
}

function Accueil() {
  const { appel } = useAdmin()
  const [tables, setTables] = useState<Resume[] | null>(null)
  const [erreur, setErreur] = useState<unknown>(null)

  useEffect(() => {
    appel<Resume[]>('/api/donnees').then(setTables).catch(setErreur)
  }, [appel])

  return (
    <div className="gestion">
      <section className="gestion__bloc">
        <h1>Données</h1>
        <p className="gestion__aide">
          Une page par table de la base, avec toutes les lignes et toutes les colonnes. Les mêmes données sont servies en JSON par
          l’API : <code>/api/donnees/&lt;table&gt;</code>, ouverte pour les tables du catalogue et réservée au gérant pour les
          commandes, billets, contrôles et comptes.
        </p>
        {erreur ? <Erreur erreur={erreur} /> : null}
        {!tables && !erreur ? <Chargement /> : null}
        {tables && (
          <ul className="donnees-cartes">
            {tables.map((t) => (
              <li key={t.nom}>
                <Link className="donnees-carte" to={`/admin/donnees/${t.nom}`}>
                  <span className="donnees-carte__titre">{t.titre}</span>
                  <span className="donnees-carte__nombre">{t.total.toLocaleString('fr-FR')}</span>
                  <span className="donnees-carte__texte">{DESCRIPTIONS[t.nom]}</span>
                  <span className="donnees-carte__pied">
                    <code>{t.url}</code>
                    {t.protegee && <span className="badge">gérant</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function Liste() {
  const { appel } = useAdmin()
  const { table } = useParams()
  const [recherche, setRecherche] = useSearchParams()
  const numero = Math.max(1, Number(recherche.get('page')) || 1)
  const [page, setPage] = useState<Page | null>(null)
  const [erreur, setErreur] = useState<unknown>(null)

  useEffect(() => {
    setPage(null)
    setErreur(null)
    appel<Page>(`/api/donnees/${table}?limite=${PAR_PAGE}&decalage=${(numero - 1) * PAR_PAGE}`)
      .then(setPage)
      .catch(setErreur)
  }, [appel, table, numero])

  const derniere = page ? Math.max(1, Math.ceil(page.total / PAR_PAGE)) : 1
  const cle = page?.colonnes.find((c) => c.cle_primaire)?.nom
  const aller = (n: number) => setRecherche(n > 1 ? { page: String(n) } : {})

  return (
    <div className="gestion">
      <section className="gestion__bloc">
        <p className="fil">
          <Link to="/admin/donnees">Données</Link>
        </p>
        <h1>{page?.titre ?? table}</h1>
        {erreur ? <Erreur erreur={erreur} /> : null}
        {!page && !erreur ? <Chargement /> : null}
        {page && (
          <>
            <p className="gestion__aide">
              {page.total.toLocaleString('fr-FR')} ligne{page.total > 1 ? 's' : ''}, {page.colonnes.length} colonnes. Cliquez sur la
              clé d’une ligne pour son détail.
            </p>
            <div className="tableau-defilant">
              <table className="tableau tableau--donnees">
                <thead>
                  <tr>
                    {page.colonnes.map((c) => (
                      <th key={c.nom} title={`${c.type}${c.reference ? `, référence ${c.reference}` : ''}`}>
                        {c.nom}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.lignes.map((ligne, i) => (
                    <tr key={i}>
                      {page.colonnes.map((c) => (
                        <td key={c.nom} title={typeof ligne[c.nom] === 'string' ? (ligne[c.nom] as string) : undefined}>
                          {c.nom === cle ? (
                            <Link to={`/admin/donnees/${table}/${encodeURIComponent(String(ligne[c.nom]))}`}>
                              <Cellule valeur={ligne[c.nom]} colonne={c} />
                            </Link>
                          ) : (
                            <Cellule valeur={ligne[c.nom]} colonne={c} />
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.lignes.length === 0 && <p className="etat-vide">Cette table est vide.</p>}
            {derniere > 1 && (
              <nav className="pagination" aria-label="Pages de la table">
                <button type="button" className="bouton bouton--petit" disabled={numero <= 1} onClick={() => aller(numero - 1)}>
                  Précédente
                </button>
                <span>
                  Page {numero} sur {derniere}
                </span>
                <button type="button" className="bouton bouton--petit" disabled={numero >= derniere} onClick={() => aller(numero + 1)}>
                  Suivante
                </button>
              </nav>
            )}
          </>
        )}
      </section>
    </div>
  )
}

function Detail() {
  const { appel } = useAdmin()
  const { table, cle } = useParams()
  const [ligne, setLigne] = useState<Ligne | null>(null)
  const [meta, setMeta] = useState<Page | null>(null)
  const [erreur, setErreur] = useState<unknown>(null)

  useEffect(() => {
    setLigne(null)
    setErreur(null)
    Promise.all([
      appel<Ligne>(`/api/donnees/${table}/${encodeURIComponent(cle ?? '')}`),
      appel<Page>(`/api/donnees/${table}?limite=1`),
    ])
      .then(([l, m]) => {
        setLigne(l)
        setMeta(m)
      })
      .catch(setErreur)
  }, [appel, table, cle])

  return (
    <div className="gestion">
      <section className="gestion__bloc">
        <p className="fil">
          <Link to="/admin/donnees">Données</Link> / <Link to={`/admin/donnees/${table}`}>{meta?.titre ?? table}</Link>
        </p>
        <h1>
          {meta?.titre ?? table}, {cle}
        </h1>
        {erreur ? <Erreur erreur={erreur} /> : null}
        {!ligne && !erreur ? <Chargement /> : null}
        {ligne && meta && (
          <dl className="detail">
            {meta.colonnes.map((c) => (
              <div key={c.nom}>
                <dt>
                  {c.nom}
                  <span className="detail__type">{c.type}</span>
                </dt>
                <dd>
                  {c.reference && ligne[c.nom] !== null ? (
                    <Link to={`/admin/donnees/${routeDeTable(c.reference)}/${encodeURIComponent(String(ligne[c.nom]))}`}>
                      <Cellule valeur={ligne[c.nom]} colonne={c} />
                    </Link>
                  ) : (
                    <Cellule valeur={ligne[c.nom]} colonne={c} />
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </div>
  )
}

export default function Donnees() {
  return (
    <Routes>
      <Route index element={<Accueil />} />
      <Route path=":table" element={<Liste />} />
      <Route path=":table/:cle" element={<Detail />} />
    </Routes>
  )
}
