export default function Card({ title, children, className = '' }) {
  return (
    <section className={["card", className].filter(Boolean).join(' ')}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </section>
  )
}
