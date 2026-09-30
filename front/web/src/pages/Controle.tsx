import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'

import { ErreurApi, verification } from '../api.ts'
import Connexion from '../components/Connexion.tsx'
import { useSession } from '../session.ts'
import type { Verdict } from '../types.ts'

type Passage = Verdict & { moment: Date }

// détecteur chargé à la demande : le wasm de ZXing n'est utile qu'au contrôle
async function creerDetecteur() {
  const [{ BarcodeDetector, prepareZXingModule }, { default: wasm }] = await Promise.all([
    import('barcode-detector/ponyfill'),
    import('zxing-wasm/reader/zxing_reader.wasm?url'),
  ])
  prepareZXingModule({
    overrides: { locateFile: (chemin: string, prefixe: string) => (chemin.endsWith('.wasm') ? wasm : prefixe + chemin) },
  })
  return new BarcodeDetector({ formats: ['qr_code'] })
}

const TITRES: Record<string, string> = {
  accepte: 'Entrée validée',
  hors_ligne: 'Entrée validée',
  deja_utilise: 'Déjà utilisé',
  rembourse: 'Billet remboursé',
  signature_invalide: 'Billet refusé',
  inconnu: 'Billet refusé',
}

export default function Controle() {
  const { session, connecter, deconnecter } = useSession('controle')
  const [poste, setPoste] = useState(() => {
    try {
      return localStorage.getItem('cinetint.poste') ?? ''
    } catch {
      return ''
    }
  })
  const [camera, setCamera] = useState<'arretee' | 'demarrage' | 'active' | 'refusee'>('arretee')
  const [verdict, setVerdict] = useState<Passage | null>(null)
  const [historique, setHistorique] = useState<Passage[]>([])
  const [saisie, setSaisie] = useState('')
  const [erreur, setErreur] = useState<string | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const flux = useRef<MediaStream | null>(null)
  const dernier = useRef<{ jeton: string; moment: number } | null>(null)
  const occupe = useRef(false)

  const verifier = useCallback(
    async (jeton: string) => {
      if (!session || occupe.current) return
      occupe.current = true
      setErreur(null)
      try {
        const resultat = await verification<Verdict>('/verification', {
          method: 'POST',
          jeton: session.jeton,
          body: JSON.stringify({ jeton: jeton.trim(), poste }),
        })
        const passage = { ...resultat, moment: new Date() }
        setVerdict(passage)
        setHistorique((h) => [passage, ...h].slice(0, 8))
        if (resultat.verdict === 'refuse') navigator.vibrate?.([120, 60, 120])
      } catch (e) {
        const err = e as ErreurApi
        if (err.statut === 401) deconnecter()
        setErreur(err.message)
      } finally {
        occupe.current = false
      }
    },
    [session, poste, deconnecter],
  )

  // le verdict s'efface seul pour enchaîner les spectateurs
  useEffect(() => {
    if (!verdict) return
    const minuteur = window.setTimeout(() => setVerdict(null), 2800)
    return () => window.clearTimeout(minuteur)
  }, [verdict])

  function arreterCamera() {
    flux.current?.getTracks().forEach((piste) => piste.stop())
    flux.current = null
    setCamera('arretee')
  }

  useEffect(() => arreterCamera, [])

  async function demarrerCamera() {
    setCamera('demarrage')
    try {
      const [detecteur, media] = await Promise.all([
        creerDetecteur(),
        navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false }),
      ])
      flux.current = media
      const element = video.current!
      element.srcObject = media
      await element.play()
      setCamera('active')
      const lire = async () => {
        if (!flux.current) return
        try {
          const codes = await detecteur.detect(element)
          const jeton = codes[0]?.rawValue
          const maintenant = Date.now()
          // un même code tenu devant la caméra n'est envoyé qu'une fois
          if (jeton && !(dernier.current?.jeton === jeton && maintenant - dernier.current.moment < 4000)) {
            dernier.current = { jeton, moment: maintenant }
            await verifier(jeton)
          }
        } catch {
          // image illisible : on passe à la suivante
        }
        window.setTimeout(lire, 250)
      }
      lire()
    } catch {
      setCamera('refusee')
    }
  }

  function envoyerSaisie(e: FormEvent) {
    e.preventDefault()
    if (saisie.trim()) verifier(saisie)
    setSaisie('')
  }

  function changerPoste(valeur: string) {
    setPoste(valeur)
    try {
      localStorage.setItem('cinetint.poste', valeur)
    } catch {
      // sans stockage, le poste sera simplement à ressaisir
    }
  }

  if (!session)
    return (
      <Connexion
        titre="Contrôle des billets"
        texte="Réservé au personnel d’accueil. Le scan vérifie la signature du billet puis le marque comme utilisé."
        identifiantSuggere="controleur"
        onConnexion={connecter}
      />
    )

  return (
    <div className="controle page">
      <div className="controle__barre">
        <div className="champ controle__poste">
          <label htmlFor="poste">Poste de contrôle</label>
          <input id="poste" value={poste} placeholder="Entrée salle Lumière" onChange={(e) => changerPoste(e.target.value)} />
        </div>
        <button type="button" className="lien" onClick={deconnecter}>
          Se déconnecter ({session.identifiant})
        </button>
      </div>

      <section className="scanner" aria-label="Lecteur de QR code">
        <video ref={video} className="scanner__video" muted playsInline hidden={camera !== 'active'} />
        {camera === 'active' ? (
          <>
            <div className="scanner__viseur" aria-hidden="true" />
            <button type="button" className="bouton bouton--petit scanner__arret" onClick={arreterCamera}>
              Arrêter la caméra
            </button>
          </>
        ) : (
          <div className="scanner__repos">
            <p>
              {camera === 'refusee'
                ? 'La caméra n’est pas accessible. Autorisez-la dans le navigateur ou saisissez le code ci-dessous.'
                : 'Présentez le QR code du billet devant la caméra.'}
            </p>
            <button type="button" className="bouton bouton--plein" onClick={demarrerCamera} disabled={camera === 'demarrage'}>
              {camera === 'demarrage' ? 'Ouverture…' : 'Activer la caméra'}
            </button>
          </div>
        )}
      </section>

      <form className="controle__saisie" onSubmit={envoyerSaisie}>
        <label htmlFor="code">Code du billet</label>
        <div>
          <input id="code" value={saisie} onChange={(e) => setSaisie(e.target.value)} placeholder="CIN1.…" autoComplete="off" />
          <button className="bouton" disabled={!saisie.trim()}>
            Vérifier
          </button>
        </div>
      </form>

      {erreur && (
        <p className="message message--alerte" role="alert">
          {erreur}
        </p>
      )}

      {historique.length > 0 && (
        <section className="controle__historique" aria-label="Derniers passages">
          <h2>Derniers passages</h2>
          <ol>
            {historique.map((p, i) => (
              <li key={i} className={`passage passage--${p.verdict}`}>
                <span className="passage__heure">
                  {p.moment.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
                <span className="passage__verdict">{TITRES[p.code] ?? p.motif}</span>
                <span className="passage__detail">
                  {[p.billet?.place, p.billet?.film].filter(Boolean).join(', ') || p.motif}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {verdict && (
        <button
          type="button"
          className={`verdict verdict--${verdict.code === 'hors_ligne' ? 'degrade' : verdict.verdict}`}
          onClick={() => setVerdict(null)}
          aria-live="assertive"
        >
          <span className="verdict__titre">{TITRES[verdict.code] ?? 'Billet refusé'}</span>
          <span className="verdict__motif">
            {verdict.code === 'deja_utilise' && verdict.billet?.utilise_le
              ? `Présenté une première fois à ${new Date(verdict.billet.utilise_le).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`
              : verdict.motif}
          </span>
          {verdict.billet?.place && (
            <span className="verdict__billet">
              <strong>{verdict.billet.place}</strong>
              {verdict.billet.film && <span>{verdict.billet.film}</span>}
              {verdict.billet.salle && <span>{verdict.billet.salle}</span>}
              {verdict.billet.seance && <span className="capitalise">{verdict.billet.seance}</span>}
            </span>
          )}
        </button>
      )}
    </div>
  )
}
