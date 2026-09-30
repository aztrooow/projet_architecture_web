import 'vite/modulepreload-polyfill'
import './styles/index.css'

import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'

import Commande from './pages/Commande.tsx'
import Introuvable from './pages/Introuvable.tsx'
import Paiement from './pages/Paiement.tsx'
import SeancePage from './pages/Seance.tsx'

// les outils du personnel ne sont pas chargés sur le parcours d'achat
const Admin = lazy(() => import('./pages/admin/Admin.tsx'))
const Controle = lazy(() => import('./pages/Controle.tsx'))

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <BrowserRouter>
      <Suspense fallback={<div className="page squelette squelette--tableau" aria-busy="true" />}>
        <Routes>
          <Route path="/seances/:id" element={<SeancePage />} />
          <Route path="/paiement/:id" element={<Paiement />} />
          <Route path="/commande/:id" element={<Commande />} />
          <Route path="/controle" element={<Controle />} />
          <Route path="/admin/*" element={<Admin />} />
          <Route path="*" element={<Introuvable />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  </StrictMode>,
)
