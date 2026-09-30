import { useCallback, useMemo } from 'react'
import { NavLink, Route, Routes } from 'react-router'

import { api, ErreurApi } from '../../api.ts'
import Connexion from '../../components/Connexion.tsx'
import { useSession } from '../../session.ts'
import Billets from './Billets.tsx'
import { AdminContexte } from './contexte.ts'
import Controles from './Controles.tsx'
import Parametres from './Parametres.tsx'
import Programmation from './Programmation.tsx'
import Remplissage from './Remplissage.tsx'
import Tarifs from './Tarifs.tsx'

const RUBRIQUES = [
  { chemin: '/admin', libelle: 'Remplissage', fin: true },
  { chemin: '/admin/programmation', libelle: 'Programmation' },
  { chemin: '/admin/tarifs', libelle: 'Tarifs' },
  { chemin: '/admin/billets', libelle: 'Billets' },
  { chemin: '/admin/controles', libelle: 'Contrôles' },
  { chemin: '/admin/parametres', libelle: 'Paramètres' },
]

export default function Admin() {
  const { session, connecter, deconnecter } = useSession('gerant')

  const appel = useCallback(
    async <T,>(chemin: string, options?: RequestInit) => {
      try {
        return await api<T>(chemin, { ...options, jeton: session?.jeton })
      } catch (e) {
        if ((e as ErreurApi).statut === 401) deconnecter()
        throw e
      }
    },
    [session, deconnecter],
  )
  const contexte = useMemo(() => (session ? { appel, jeton: session.jeton } : null), [appel, session])

  if (!session || !contexte)
    return (
      <Connexion
        titre="Espace gérant"
        texte="Programmation, tarifs, remplissage des salles et remboursements."
        identifiantSuggere="gerant"
        onConnexion={async (identifiant, motDePasse) => {
          const s = await connecter(identifiant, motDePasse)
          if (s.role !== 'gerant') {
            deconnecter()
            throw new ErreurApi(403, 'Ce compte n’a pas accès à l’espace gérant')
          }
        }}
      />
    )

  return (
    <AdminContexte.Provider value={contexte}>
      <div className="admin page">
        <div className="admin__barre">
          <nav className="admin__nav" aria-label="Rubriques de l’espace gérant">
            {RUBRIQUES.map((r) => (
              <NavLink key={r.chemin} to={r.chemin} end={r.fin}>
                {r.libelle}
              </NavLink>
            ))}
          </nav>
          <button type="button" className="lien" onClick={deconnecter}>
            Se déconnecter
          </button>
        </div>
        <Routes>
          <Route index element={<Remplissage />} />
          <Route path="programmation" element={<Programmation />} />
          <Route path="tarifs" element={<Tarifs />} />
          <Route path="billets" element={<Billets />} />
          <Route path="controles" element={<Controles />} />
          <Route path="parametres" element={<Parametres />} />
        </Routes>
      </div>
    </AdminContexte.Provider>
  )
}
