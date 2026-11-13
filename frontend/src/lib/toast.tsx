import { AnimatePresence, motion } from 'framer-motion'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type T = { id: number; text: string; err?: boolean }
const Ctx = createContext<(text: string, err?: boolean) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<T[]>([])
  const push = useCallback((text: string, err = false) => {
    const id = Date.now() + Math.random()
    setItems((x) => [...x, { id, text, err }])
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 5200)
  }, [])
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="toast-host" role="status" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div key={t.id} className={`toast ${t.err ? 'err' : ''}`}
              initial={{ x: 120, rotate: 6, opacity: 0 }} animate={{ x: 0, rotate: 0, opacity: 1 }}
              exit={{ x: 160, opacity: 0 }} transition={{ type: 'spring', stiffness: 380, damping: 28 }}>
              {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  )
}
export const useToast = () => useContext(Ctx)
