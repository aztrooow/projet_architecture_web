const fuseau = 'Europe/Paris'

export const euros = (centimes: number) =>
  (centimes / 100).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })

export const heure = (iso: string) =>
  new Date(iso).toLocaleTimeString('fr-FR', { hour: 'numeric', minute: '2-digit', timeZone: fuseau }).replace(':', 'h')

export const dateLongue = (iso: string) =>
  new Date(iso).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: fuseau })

export const dateHeure = (iso: string) => `${dateLongue(iso)} à ${heure(iso)}`

export const duree = (minutes: number) => `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`

export const typeProduction = (code: string) => ({ '3d': '3D', art_essai: 'Art et essai' })[code] ?? ''

export const place = (b: { rang: string; numero: number }) => `${b.rang}${b.numero}`
