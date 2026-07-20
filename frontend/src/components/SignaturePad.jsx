import { useEffect, useRef, useState } from 'react'

const INK = '#111827'
const MIN_WIDTH = 2.2
const MAX_WIDTH = 3.4

export default function SignaturePad({ value = '', onChange }) {
  const canvasRef = useRef(null)
  const drawingRef = useRef(false)
  const pointsRef = useRef([])
  const historyRef = useRef([])
  const [hasSignature, setHasSignature] = useState(Boolean(value))
  const [preview, setPreview] = useState(value || '')

  const setupContext = () => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const ctx = canvas.getContext('2d')
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = INK
    ctx.fillStyle = INK
    ctx.lineWidth = MIN_WIDTH
    ctx.imageSmoothingEnabled = true
    ctx.setLineDash([]) // force solid strokes
    return ctx
  }

  const snapshot = () => {
    const canvas = canvasRef.current
    if (!canvas) return ''
    return canvas.toDataURL('image/png')
  }

  const restore = (dataUrl) => {
    const canvas = canvasRef.current
    const ctx = setupContext()
    if (!canvas || !ctx) return
    const rect = canvas.getBoundingClientRect()
    ctx.clearRect(0, 0, rect.width, rect.height)
    if (!dataUrl) return
    const img = new Image()
    img.onload = () => {
      ctx.drawImage(img, 0, 0, rect.width, rect.height)
      setupContext()
    }
    img.src = dataUrl
  }

  const resizeCanvas = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const ratio = Math.max(window.devicePixelRatio || 1, 1)
    const previous = hasSignature ? snapshot() : value

    canvas.width = Math.round(rect.width * ratio)
    canvas.height = Math.round(rect.height * ratio)
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`

    const ctx = canvas.getContext('2d')
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    setupContext()
    if (previous) restore(previous)
  }

  useEffect(() => {
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)
    return () => window.removeEventListener('resize', resizeCanvas)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (value && value !== preview) {
      setPreview(value)
      setHasSignature(true)
      restore(value)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const getPoint = (event) => {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
      t: event.timeStamp || Date.now(),
      pressure: event.pressure && event.pressure > 0 ? event.pressure : 0.5,
    }
  }

  const drawDot = (point) => {
    const ctx = setupContext()
    if (!ctx) return
    const width = MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * point.pressure
    ctx.beginPath()
    ctx.arc(point.x, point.y, width / 2, 0, Math.PI * 2)
    ctx.fill()
  }

  const drawSolidSegment = (from, to) => {
    const ctx = setupContext()
    if (!ctx) return
    const dx = to.x - from.x
    const dy = to.y - from.y
    const distance = Math.sqrt(dx * dx + dy * dy)
    const speed = distance / Math.max(to.t - from.t, 1)
    const pressureWidth = MIN_WIDTH + (MAX_WIDTH - MIN_WIDTH) * to.pressure
    const speedWidth = Math.max(MIN_WIDTH, MAX_WIDTH - speed * 0.35)
    ctx.lineWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (pressureWidth + speedWidth) / 2))
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.stroke()
  }

  const drawEventPoints = (event) => {
    const events = typeof event.getCoalescedEvents === 'function' ? event.getCoalescedEvents() : [event]
    for (const pointerEvent of events) {
      const point = getPoint(pointerEvent)
      const points = pointsRef.current
      const last = points[points.length - 1]
      if (!last) {
        points.push(point)
        drawDot(point)
        continue
      }
      drawSolidSegment(last, point)
      points.push(point)
    }
  }

  const commit = () => {
    const data = snapshot()
    setPreview(data)
    setHasSignature(true)
    onChange?.(data)
  }

  const start = (event) => {
    event.preventDefault()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    historyRef.current.push(snapshot())
    if (historyRef.current.length > 10) historyRef.current.shift()
    drawingRef.current = true
    pointsRef.current = []
    drawEventPoints(event)
  }

  const move = (event) => {
    if (!drawingRef.current) return
    event.preventDefault()
    drawEventPoints(event)
  }

  const end = (event) => {
    if (!drawingRef.current) return
    event?.preventDefault?.()
    drawEventPoints(event)
    drawingRef.current = false
    pointsRef.current = []
    event?.currentTarget?.releasePointerCapture?.(event.pointerId)
    commit()
  }

  const clear = () => {
    const canvas = canvasRef.current
    const ctx = setupContext()
    if (!canvas || !ctx) return
    const rect = canvas.getBoundingClientRect()
    historyRef.current.push(snapshot())
    ctx.clearRect(0, 0, rect.width, rect.height)
    setHasSignature(false)
    setPreview('')
    onChange?.('')
  }

  const undo = () => {
    const previous = historyRef.current.pop()
    if (previous === undefined) return
    restore(previous)
    const isBlank = !previous || previous === snapshot()
    setPreview(previous || '')
    setHasSignature(Boolean(previous) && !isBlank)
    onChange?.(previous || '')
  }

  return (
    <div className="signature-box signature-pad-upgraded">
      <div className="signature-header-row">
        <label>Signature</label>
        {preview && <img src={preview} alt="Signature preview" className="signature-preview" />}
      </div>
      <canvas
        ref={canvasRef}
        className="signature-canvas signature-canvas-solid"
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        onPointerLeave={end}
      />
      <div className="button-row compact signature-actions">
        <button type="button" className="secondary" onClick={clear}>Clear signature</button>
        <button type="button" className="secondary" onClick={undo} disabled={!historyRef.current.length}>Undo</button>
        <span className={hasSignature ? 'success small' : 'muted small'}>{hasSignature ? 'Signature captured' : 'Draw signature before sign in/out'}</span>
      </div>
    </div>
  )
}
