import RemovalSettings from '../components/RemovalSettings'
import ReceiptSettings from '../components/ReceiptSettings'

export default function CommissionSettingsPage() {
  return <section className="mortuary-book">
    <header className="form-card"><h1>Commissions</h1><p>Set Employee and Assistant amounts for every commission item in the table below. Working hours are maintained in Add/Edit Staff.</p><p className="muted">Staff enter their own service claims. Matching Mortuary Book, Invoice and Receipts covering the full invoice are required. Validated claims show green expected amounts; missing or mismatched evidence shows red. The franchise holder approves service claims before they become earned commissions.</p></header>
    <RemovalSettings />
    <ReceiptSettings />
  </section>
}
