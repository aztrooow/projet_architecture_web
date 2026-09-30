// Comportements des pages rendues par le serveur (accueil, fiche film, borne).
import 'vite/modulepreload-polyfill'
import './styles/index.css'

const racine = document.documentElement

function ouverture() {
  const intro = document.querySelector<HTMLElement>('[data-intro]')
  if (!intro || !racine.classList.contains('avec-intro')) return
  const terminer = () => {
    racine.classList.remove('avec-intro')
    intro.remove()
    try {
      sessionStorage.setItem('cinetint.intro', '1')
    } catch {
      // navigation privée : l'ouverture rejouera, ce n'est pas grave
    }
  }
  requestAnimationFrame(() => intro.classList.add('intro--joue'))
  const minuteur = window.setTimeout(terminer, 3050)
  // un clic ou Échap coupe l'ouverture
  const passer = () => {
    window.clearTimeout(minuteur)
    terminer()
  }
  intro.addEventListener('click', passer, { once: true })
  window.addEventListener('keydown', (e) => e.key === 'Escape' && passer(), { once: true })
}

function apparitions() {
  const elements = document.querySelectorAll<HTMLElement>('[data-revele]')
  if (!('IntersectionObserver' in window)) {
    elements.forEach((el) => el.classList.add('est-visible'))
    return
  }
  const observateur = new IntersectionObserver(
    (entrees) => {
      for (const entree of entrees) {
        if (entree.isIntersecting) {
          entree.target.classList.add('est-visible')
          observateur.unobserve(entree.target)
        }
      }
    },
    { rootMargin: '0px 0px -10% 0px' },
  )
  elements.forEach((el) => observateur.observe(el))
}

function enteteSurLaPhoto() {
  const entete = document.querySelector('[data-entete]')
  const hero = document.querySelector('[data-hero]')
  if (!entete || !hero) return
  new IntersectionObserver(([entree]) => entete.classList.toggle('entete--opaque', !entree.isIntersecting), {
    rootMargin: '-72px 0px 0px 0px',
    threshold: 0.02,
  }).observe(hero)
}

function compteurs() {
  const valeurs = document.querySelectorAll<HTMLElement>('[data-compteur]')
  const format = new Intl.NumberFormat('fr-FR')
  const observateur = new IntersectionObserver((entrees) => {
    for (const entree of entrees) {
      if (!entree.isIntersecting) continue
      const el = entree.target as HTMLElement
      observateur.unobserve(el)
      const cible = Number(el.dataset.compteur)
      const debut = performance.now()
      const pas = (t: number) => {
        const avance = Math.min(1, (t - debut) / 1400)
        const adouci = 1 - Math.pow(1 - avance, 4)
        el.textContent = format.format(Math.round(cible * adouci))
        if (avance < 1) requestAnimationFrame(pas)
      }
      requestAnimationFrame(pas)
    }
  })
  valeurs.forEach((el) => observateur.observe(el))
}

function onglets() {
  const bloc = document.querySelector('[data-onglets]')
  if (!bloc) return
  const liste = [...bloc.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
  const choisir = (onglet: HTMLButtonElement) => {
    for (const autre of liste) {
      const actif = autre === onglet
      autre.setAttribute('aria-selected', String(actif))
      autre.tabIndex = actif ? 0 : -1
      document.getElementById(autre.getAttribute('aria-controls')!)!.hidden = !actif
    }
    onglet.focus()
  }
  liste.forEach((onglet, i) => {
    onglet.addEventListener('click', () => choisir(onglet))
    onglet.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') choisir(liste[(i + 1) % liste.length])
      if (e.key === 'ArrowLeft') choisir(liste[(i - 1 + liste.length) % liste.length])
    })
  })
}

function borne() {
  const horloge = document.querySelector('[data-horloge]')
  if (!horloge) return
  const maj = () => {
    horloge.textContent = new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  }
  maj()
  window.setInterval(maj, 15_000)
  // les horaires passés disparaissent : on recharge la liste chaque minute
  window.setInterval(() => window.location.reload(), 60_000)
}

ouverture()
apparitions()
enteteSurLaPhoto()
compteurs()
onglets()
borne()
