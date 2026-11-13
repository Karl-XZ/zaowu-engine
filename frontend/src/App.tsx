import { lazy, Suspense } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { Crosshair, GenerationMode, Nav, PageWipe } from './components/Chrome'
import { useEffect } from 'react'
import Home from './pages/Home'
import { Admin, Login, Me, NotFound, Pay, PayMock, Rules } from './pages/Misc'

const Create = lazy(() => import('./pages/Create'))
const Cad = lazy(() => import('./pages/Cad'))
const TaskPage = lazy(() => import('./pages/Model').then((m) => ({ default: m.TaskPage })))
const ModelPage = lazy(() => import('./pages/Model').then((m) => ({ default: m.ModelPage })))

function ScrollTop() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' })
    else window.scrollTo(0, 0)
  }, [pathname, hash])
  return null
}

export default function App() {
  const { pathname } = useLocation()
  const compact = pathname !== '/'
  return (
    <>
      <a href="#main" className="sr-only">跳到主要内容</a>
      <Nav compact={compact} />
      <GenerationMode />
      <ScrollTop />
      <PageWipe />
      <Crosshair />
      <div id="main">
        <Suspense fallback={<div className="loading-stripes" style={{ height: 8 }} />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/login" element={<Login />} />
            <Route path="/create" element={<Create />} />
            <Route path="/create/:sid" element={<Create />} />
            <Route path="/cad" element={<Cad />} />
            <Route path="/tasks/:tid" element={<TaskPage />} />
            <Route path="/models/:mid" element={<ModelPage />} />
            <Route path="/pay" element={<Pay />} />
            <Route path="/pay/mock" element={<PayMock />} />
            <Route path="/me" element={<Me />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/rules" element={<Rules />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </div>
    </>
  )
}
