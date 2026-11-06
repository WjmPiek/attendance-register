import { useStaffNavigation } from '../api/staffNavigation'
import MortuaryBook from '../components/MortuaryBook'
import MFFileReceipt from '../components/MFFileReceipt'
import MFInvoice from '../components/MFInvoice'
import CommissionDocumentRegister from '../components/CommissionDocumentRegister'

export default function UploadProofPage() {
  const [route, navigate] = useStaffNavigation()
  if(route.page==='documents') return <CommissionDocumentRegister onBack={()=>navigate('proof')}/>
  const types = { invoices: ['MF Invoice', MFInvoice], receipts: ['MF File Receipt', MFFileReceipt], mortuary: ['Mortuary Book', MortuaryBook] }
  const selected = types[route.page]
  const Importer = selected?.[1]
  return <section className="mortuary-book"><header className="form-card"><h1>Upload proof</h1><p>Upload the Mortuary Book, Invoice and all payment Receipts. Documents must match and receipts must balance the invoice before commissions are allocated.</p><button type="button" className="glass-button" onClick={()=>navigate('documents')}>Commission documents and activity log</button>{selected && <button type="button" className="glass-button" onClick={() => navigate('proof')}>← Document types</button>}</header>{Importer ? <Importer canManage={false}/> : <nav className="staff-proof-links">{Object.entries(types).map(([id, [label]]) => <section className="staff-proof-card" key={id}><strong>{label}</strong><button type="button" className="link-button" onClick={() => navigate(id)}>Import file →</button></section>)}</nav>}</section>
}
