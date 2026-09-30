export type Film = {
  id: number
  titre: string
  realisation: string
  annee: number | null
  duree_min: number
  genre: string
  synopsis: string
  type_production: 'standard' | '3d' | 'art_essai'
  couleur: string
  affiche_url: string | null
  image_url: string | null
  actif?: boolean
}

export type Evenement = { id: number; nom: string; description: string }

export type Tarif = {
  categorie: string
  categorie_libelle: string
  libelle: string
  prix_centimes: number
}

export type Seance = {
  id: number
  debut: string
  version: string
  film: Film
  salle: { id: number; nom: string; capacite: number }
  evenement: Evenement | null
  vendus: number
  tarifs: Tarif[]
  places_max: number
  duree_verrou_min: number
  commencee: boolean
}

export type EtatSiege = 'libre' | 'verrouille' | 'vendu' | 'panier'

export type Siege = {
  id: number
  rang: string
  numero: number
  x: number
  y: number
  pmr: boolean
  etat: EtatSiege
}

export type Plan = { seance_id: number; largeur: number; profondeur: number; sieges: Siege[] }

export type Ligne = {
  siege_id: number
  rang: string
  numero: number
  categorie: string
  libelle: string
  prix_centimes: number
}

export type Billet = {
  id: string
  rang: string
  numero: number
  categorie: string
  libelle_tarif: string
  prix_centimes: number
  statut: 'valide' | 'utilise' | 'rembourse'
  jeton: string | null
  utilise_le: string | null
  rembourse_le: string | null
}

export type Commande = {
  id: string
  reference: string
  statut: 'en_attente' | 'payee' | 'expiree' | 'annulee'
  canal: 'web' | 'borne'
  montant_centimes: number
  expire_le: string
  psp_session: string | null
  seance: Omit<Seance, 'vendus' | 'tarifs' | 'places_max' | 'duree_verrou_min' | 'commencee'>
  lignes: Ligne[]
  remboursable_jusqua: string
  billets: Billet[]
}

export type Verdict = {
  verdict: 'accepte' | 'refuse'
  code: string
  motif: string
  billet?: { film?: string; seance?: string; salle?: string; place?: string; tarif?: string; utilise_le?: string | null }
}
