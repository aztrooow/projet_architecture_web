// Adresses des services injectées par le serveur front (vides = même origine)
type Configuration = { api: string; qr: string; verification: string }

const configuration: Configuration = (window as unknown as { CINETINT?: Configuration }).CINETINT ?? {
  api: '',
  qr: '',
  verification: '',
}

export class ErreurApi extends Error {
  statut: number
  details: unknown

  constructor(statut: number, message: string, details?: unknown) {
    super(message)
    this.statut = statut
    this.details = details
  }
}

function lireMessage(detail: unknown, statut: number): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
  if (Array.isArray(detail)) return 'Données invalides'
  return statut >= 500 ? 'Le service ne répond pas, réessayez dans un instant' : 'Requête refusée'
}

async function appeler<T>(url: string, options: RequestInit & { jeton?: string | null } = {}): Promise<T> {
  const { jeton, ...init } = options
  const entetes = new Headers(init.headers)
  if (init.body && !entetes.has('Content-Type')) entetes.set('Content-Type', 'application/json')
  if (jeton) entetes.set('Authorization', `Bearer ${jeton}`)
  let reponse: Response
  try {
    reponse = await fetch(url, { ...init, headers: entetes })
  } catch {
    throw new ErreurApi(0, 'Connexion impossible, vérifiez le réseau')
  }
  if (!reponse.ok) {
    let detail: unknown
    try {
      detail = (await reponse.json()).detail
    } catch {
      detail = undefined
    }
    throw new ErreurApi(reponse.status, lireMessage(detail, reponse.status), detail)
  }
  return reponse.json() as Promise<T>
}

export const api = <T>(chemin: string, options?: RequestInit & { jeton?: string | null }) =>
  appeler<T>(configuration.api + chemin, options)

export const verification = <T>(chemin: string, options?: RequestInit & { jeton?: string | null }) =>
  appeler<T>(configuration.verification + chemin, options)

export const urlApi = (chemin: string) => configuration.api + chemin
export const urlQr = (jeton: string) => `${configuration.qr}/qr/${jeton}.svg`
