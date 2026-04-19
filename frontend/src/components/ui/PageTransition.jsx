import { motion, AnimatePresence } from 'framer-motion'
import { useLocation } from 'react-router-dom'

const variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
}

const transition = { duration: 0.15 }

export function PageTransition({ children }) {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        variants={variants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={transition}
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minHeight: 0,
        }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

export function FadeIn({ children, delay = 0, style = {} }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      style={style}
    >
      {children}
    </motion.div>
  )
}

export function ScaleIn({ children, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, delay }}
    >
      {children}
    </motion.div>
  )
}

export function Pressable({ children, onPress, style = {}, disabled = false }) {
  return (
    <motion.div
      whileTap={disabled ? {} : { scale: 0.97, opacity: 0.85 }}
      transition={{ duration: 0.1 }}
      onClick={disabled ? undefined : onPress}
      style={{ cursor: disabled ? 'not-allowed' : 'pointer', ...style }}
    >
      {children}
    </motion.div>
  )
}

export function SlideUp({ children, visible }) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: '100%', opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: '100%', opacity: 0 }}
          transition={{ duration: 0.3 }}
          style={{
            position: 'fixed', bottom: 0, left: 0, right: 0,
            zIndex: 100, background: '#141414',
            borderRadius: '20px 20px 0 0',
            border: '1px solid #2A2A2A',
            padding: '20px 20px 40px',
            maxWidth: 430, margin: '0 auto',
          }}
        >
          <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A', margin: '0 auto 20px' }} />
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
