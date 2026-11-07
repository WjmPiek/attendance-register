import { useEffect, useRef, useState } from 'react'
import { currentCommissionMonth } from './commission-cycle.mjs'

export function useCommissionMonth() {
  const [month, setMonth] = useState(currentCommissionMonth)
  const automaticMonth = useRef(currentCommissionMonth())
  useEffect(() => {
    const timer = setInterval(() => {
      const next = currentCommissionMonth(), previous = automaticMonth.current
      if (next !== previous) {
        setMonth(selected => selected === previous ? next : selected)
        automaticMonth.current = next
      }
    }, 20000)
    return () => clearInterval(timer)
  }, [])
  return [month, setMonth]
}
