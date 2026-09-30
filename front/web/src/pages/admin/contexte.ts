import { createContext, useContext } from 'react'

type Appel = <T>(chemin: string, options?: RequestInit) => Promise<T>

export const AdminContexte = createContext<{ appel: Appel; jeton: string } | null>(null)

export function useAdmin() {
  const valeur = useContext(AdminContexte)
  if (!valeur) throw new Error('useAdmin hors de l’espace gérant')
  return valeur
}
