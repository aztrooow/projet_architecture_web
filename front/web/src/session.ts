import { useState } from 'react'

import { api } from './api.ts'

type Session = { jeton: string; role: 'gerant' | 'controleur'; identifiant: string }

// jeton du personnel gardé pour l'onglet seulement (sessionStorage)
export function useSession(espace: 'gerant' | 'controle') {
  const cle = `cinetint.session.${espace}`
  const [session, setSession] = useState<Session | null>(() => {
    try {
      const brut = sessionStorage.getItem(cle)
      if (!brut) return null
      const lue = JSON.parse(brut) as Session
      const { exp } = JSON.parse(atob(lue.jeton.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      return exp * 1000 > Date.now() ? lue : null
    } catch {
      return null
    }
  })

  async function connecter(identifiant: string, motDePasse: string) {
    const nouvelle = await api<Session>('/api/auth/connexion', {
      method: 'POST',
      body: JSON.stringify({ identifiant, mot_de_passe: motDePasse }),
    })
    try {
      sessionStorage.setItem(cle, JSON.stringify(nouvelle))
    } catch {
      // pas de stockage disponible : la session tient jusqu'au rechargement
    }
    setSession(nouvelle)
    return nouvelle
  }

  function deconnecter() {
    try {
      sessionStorage.removeItem(cle)
    } catch {
      // rien à nettoyer
    }
    setSession(null)
  }

  return { session, connecter, deconnecter }
}
