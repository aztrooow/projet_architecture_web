import { type FormEvent, useState } from 'react'

import { ErreurApi } from '../api.ts'

type Props = {
  titre: string
  texte: string
  identifiantSuggere: string
  onConnexion: (identifiant: string, motDePasse: string) => Promise<unknown>
}

export default function Connexion({ titre, texte, identifiantSuggere, onConnexion }: Props) {
  const [identifiant, setIdentifiant] = useState(identifiantSuggere)
  const [motDePasse, setMotDePasse] = useState('')
  const [erreur, setErreur] = useState<string | null>(null)
  const [envoi, setEnvoi] = useState(false)

  async function valider(e: FormEvent) {
    e.preventDefault()
    setEnvoi(true)
    setErreur(null)
    try {
      await onConnexion(identifiant, motDePasse)
    } catch (err) {
      setErreur((err as ErreurApi).message)
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <section className="connexion page page--etroite">
      <h1>{titre}</h1>
      <p className="connexion__texte">{texte}</p>
      <form className="connexion__formulaire" onSubmit={valider}>
        <div className="champ">
          <label htmlFor="identifiant">Identifiant</label>
          <input
            id="identifiant"
            autoComplete="username"
            value={identifiant}
            onChange={(e) => setIdentifiant(e.target.value)}
            required
          />
        </div>
        <div className="champ">
          <label htmlFor="mot-de-passe">Mot de passe</label>
          <input
            id="mot-de-passe"
            type="password"
            autoComplete="current-password"
            value={motDePasse}
            onChange={(e) => setMotDePasse(e.target.value)}
            required
          />
        </div>
        {erreur && (
          <p className="message message--alerte" role="alert">
            {erreur}
          </p>
        )}
        <button className="bouton bouton--plein" disabled={envoi}>
          {envoi ? 'Connexion…' : 'Se connecter'}
        </button>
      </form>
    </section>
  )
}
