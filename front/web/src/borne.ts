// La borne du hall utilise la même application, en mode kiosque.
const CLE = 'cinetint.borne'

export function estBorne(): boolean {
  const demande = new URLSearchParams(window.location.search).get('borne')
  try {
    if (demande === '1') sessionStorage.setItem(CLE, '1')
    if (demande === '0') sessionStorage.removeItem(CLE)
    return sessionStorage.getItem(CLE) === '1'
  } catch {
    return demande === '1'
  }
}
