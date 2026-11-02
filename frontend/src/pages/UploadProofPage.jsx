import { useStaffNavigation } from '../api/staffNavigation'
import MortuaryBook from '../components/MortuaryBook'
import MFFileReceipt from '../components/MFFileReceipt'
import MFInvoice from '../components/MFInvoice'

export default function UploadProofPage() {
  const [route, navigate] = useStaffNavigation()
  const types = { invoices: ['MF Invoice', MFInvoice], receipts: ['MF File Receipt', MFFileReceipt], mortuary: ['Mortuary Book', MortuaryBook] }
  const selected = types[route.page]
  const Importer = selected?.[1]
  return <section className="mortuary-book"><header className="form-card"><h1>Upload proof</h1><p>Upload the closed-file Mortuary Book, Invoice and all payment Receipts as soon as possible so staff can see their validated commission amounts.</p>{selected && <button type="button" className="glass-button" onClick={() => navigate('proof')}>← Document types</button>}</header>{Importer ? <Importer /> : <nav className="staff-proof-links">{Object.entries(types).map(([id, [label]]) => <section className="staff-proof-card" key={id}><strong>{label}</strong><button type="button" className="link-button" onClick={() => navigate(id)}>Import file →</button></section>)}</nav>}</section>
}
